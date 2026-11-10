import type { components } from "@labtrack/shared";

import { clearExports } from "@/features/emergency/export-cleanup";
import { setBiometricOn, setLocked } from "@/features/lock/lock-store";
import { setWizardActive } from "@/features/records/onboarding-store";
import { publicApi } from "@/lib/api-base";
import { setLocale } from "@/lib/i18n";
import { wipeLocalStore } from "@/lib/local-store";
import { clearLocalNotifications } from "@/lib/notifications";
import { stopCachePersistence } from "@/lib/persist";
import { queryClient } from "@/lib/query-client";

import { clearPendingActivationToken } from "./activation-link";
import { onFreshInstall } from "./install-marker";
import { type Notice, parseNotice, setNotice } from "./notice";
import { deleteSecure, readSecure, type SecureKey, secureKeys, writeSecure } from "./secure-tokens";
import {
  clearAccessToken,
  getStatus,
  setAccessToken,
  setStatus,
  tokenSubject,
} from "./session-store";

type TokenResponse = components["schemas"]["TokenResponse"];

/** "notice": the session ended for a reason the user must see (see notice.ts). */
export type RefreshOutcome = "ok" | "notice" | "signedOut" | "offline";

let inflight: Promise<RefreshOutcome> | null = null;
// Bumped by every sign-in and wipe: a refresh started in an older epoch must not write back
// (it would resurrect a session the user just ended, or overwrite a newer login).
let epoch = 0;
// True from the start of a wipe to its end: no refresh may start or write back meanwhile, and
// no queued write is sent (the status still says signedIn until the wipe's last step).
let wiping = false;

export function isWiping(): boolean {
  return wiping;
}

/** Reads the stored refresh token at startup; no network, so a cold start works offline. */
export async function restoreSession(): Promise<void> {
  try {
    // iOS keeps Keychain items after uninstall: a fresh install must not inherit a session.
    await onFreshInstall(() => deleteSecure(...(Object.values(secureKeys) as SecureKey[])));
    // An unread notice (admin reset, report, deletion) survives a restart (docs/04 §1 5a).
    const notice = parseNotice(await readSecure(secureKeys.notice));
    if (notice) {
      await wipeLocalStore().catch(() => undefined); // the notice ended the session
      setNotice(notice);
      setStatus("notice");
      return;
    }
    const signedIn = Boolean(await readSecure(secureKeys.refresh));
    // A wipe that never finished (the app died mid-sign-out) left the store's key behind.
    if (!signedIn) await wipeLocalStore().catch(() => undefined);
    // With biometric unlock on, a cold start opens locked - decided before the status flips,
    // so no signed-in screen is ever drawn first.
    const biometricOn = signedIn && (await readSecure(secureKeys.biometric)) === "on";
    setBiometricOn(biometricOn);
    if (biometricOn) setLocked(true);
    setStatus(signedIn ? "signedIn" : "signedOut");
  } catch {
    // e.g. the Keychain is unavailable while the phone is locked (background start). Do not
    // delete anything: the session may be fine once the phone is unlocked.
    setStatus("signedOut");
  }
}

/** Changes on every sign-in and wipe: work started in an older epoch must not continue. */
export function currentEpoch(): number {
  return epoch;
}

/** Stores a fresh login: the refresh token before the session counts as signed in. */
export async function establishSession(pair: TokenResponse): Promise<void> {
  epoch += 1;
  const account = tokenSubject(pair.access_token);
  // the local store opens only for this account (a store left by someone else is discarded)
  if (account) await writeSecure(secureKeys.account, account);
  else await deleteSecure(secureKeys.account);
  await writeSecure(secureKeys.refresh, pair.refresh_token);
  if (pair.device_token) await writeSecure(secureKeys.device, pair.device_token);
  setAccessToken(pair.access_token, pair.expires_in);
  setStatus("signedIn");
}

/**
 * Single-flight refresh (docs/04 §1): concurrent callers share one rotation, so the server
 * never sees the same refresh token twice from this device. The server's 20 s grace covers
 * a rotation whose response was lost.
 */
export function refreshSession(): Promise<RefreshOutcome> {
  inflight ??= runRefresh().finally(() => {
    inflight = null;
  });
  return inflight;
}

async function runRefresh(): Promise<RefreshOutcome> {
  if (wiping) return "signedOut";
  const started = epoch;
  let refreshToken: string | null;
  try {
    refreshToken = await readSecure(secureKeys.refresh);
  } catch {
    return "offline"; // Keychain not readable right now (locked phone); try again later
  }
  // Already wiped: keep the current status (e.g. a notice stays visible to the user).
  if (!refreshToken) return "signedOut";
  let result: Awaited<ReturnType<typeof postRefresh>>;
  try {
    result = await postRefresh(refreshToken);
  } catch {
    return "offline"; // keep the tokens; the next request tries again
  }
  // signed out or in again meanwhile, or a wipe is running
  if (started !== epoch || wiping) return "signedOut";
  const { data, error, response } = result;
  if (data) {
    try {
      await writeSecure(secureKeys.refresh, data.refresh_token);
    } catch {
      // The rotated token could not be kept, so the next start would replay the old one
      // (reuse detection). Fail closed instead.
      await wipeLocal("signedOut");
      return "signedOut";
    }
    setAccessToken(data.access_token, data.expires_in);
    return "ok";
  }
  if (response.status === 401) {
    // Why the session ended decides the notice (also when the response that ended it - a
    // report or a deletion request - never arrived).
    const notice: Notice | null =
      error?.code === "auth.admin_reset"
        ? { kind: "adminReset" }
        : error?.code === "auth.account_reported"
          ? { kind: "reported" }
          : error?.code === "auth.deletion_pending"
            ? { kind: "deleted" }
            : null;
    await wipeLocal(notice ?? "signedOut");
    return notice ? "notice" : "signedOut";
  }
  return "offline"; // 429 / 5xx: the session may still be valid
}

function postRefresh(refreshToken: string) {
  return publicApi.POST("/api/v1/auth/refresh", { body: { refresh_token: refreshToken } });
}

/** User sign-out: revoke the session family on the server (best effort), then wipe locally. */
export async function signOut(): Promise<void> {
  // Let a running rotation finish so we revoke the newest token, not the one it replaced.
  await inflight?.catch(() => undefined);
  const refreshToken = await readSecure(secureKeys.refresh).catch(() => null);
  if (refreshToken) {
    await publicApi
      .POST("/api/v1/auth/logout", { body: { refresh_token: refreshToken } })
      .catch(() => undefined);
  }
  await wipeLocal("signedOut");
}

/**
 * Removes every credential and cached response from the device (CLAUDE.md rule 8).
 * The trusted-device token stays on a normal sign-out (see `secureKeys.device`); it goes with
 * any notice (admin reset, report, deletion: the account is not simply signed out) or when
 * `forgetDevice` is set.
 * Also the encrypted local store (persisted cache, queued writes - its key is deleted, so
 * nothing left on disk can be read) and every scheduled or shown local notification.
 */
export async function wipeLocal(
  next: "signedOut" | Notice,
  { forgetDevice = next !== "signedOut" }: { forgetDevice?: boolean } = {},
): Promise<void> {
  epoch += 1;
  wiping = true;
  clearAccessToken();
  clearPendingActivationToken();
  setBiometricOn(false);
  setLocale("mn"); // the next user starts in the default language
  setWizardActive(false); // an unfinished onboarding is not the next session's
  await queryClient.cancelQueries();
  stopCachePersistence(); // before clear(): the persister must not save the emptied cache
  queryClient.clear();
  try {
    // The notice first: if the app dies mid-wipe, the next start still shows it (restoreSession
    // reads the notice before the refresh token).
    if (next !== "signedOut") await writeSecure(secureKeys.notice, JSON.stringify(next));
    // The biometric choice and unlock key belong to the user who signed out, not the phone.
    const keys = [
      secureKeys.refresh,
      secureKeys.biometric,
      secureKeys.unlockGate,
      secureKeys.account,
    ];
    await deleteSecure(...(forgetDevice ? [...keys, secureKeys.device] : keys));
  } finally {
    // Each part on its own: one failing never keeps the others (or the sign-out) from running.
    // the emergency card's exported files (wallet PDF, wallpaper) leave the cache too
    await Promise.allSettled([
      wipeLocalStore(),
      clearLocalNotifications(),
      Promise.resolve().then(clearExports),
    ]);
    // N2: a cache restore that was already reading may have hydrated after clear() above
    queryClient.clear();
    // anything started during the wipe belongs to no session
    epoch += 1;
    wiping = false;
    // A notice is not replaced by a later, plainer "signed out".
    if (next !== "signedOut") {
      setNotice(next);
      setStatus("notice");
    } else if (getStatus() !== "notice") {
      setStatus("signedOut");
    }
    // Only now, with the status no longer signedIn: unlocking any earlier would mount the
    // signed-in screens for a moment (and let them start requests) during the wipe.
    setLocked(false);
  }
}

/** The user has read the notice; continue signed out. */
export async function acknowledgeNotice(): Promise<void> {
  await deleteSecure(secureKeys.notice).catch(() => undefined);
  setNotice(null);
  setStatus("signedOut");
}
