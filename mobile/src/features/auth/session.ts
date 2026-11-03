import type { components } from "@labtrack/shared";

import { setBiometricOn, setLocked } from "@/features/lock/lock-store";
import { publicApi } from "@/lib/api-base";
import { setLocale } from "@/lib/i18n";
import { queryClient } from "@/lib/query-client";

import { clearPendingActivationToken } from "./activation-link";
import { onFreshInstall } from "./install-marker";
import { deleteSecure, readSecure, type SecureKey, secureKeys, writeSecure } from "./secure-tokens";
import { clearAccessToken, getStatus, setAccessToken, setStatus } from "./session-store";

type TokenResponse = components["schemas"]["TokenResponse"];

export type RefreshOutcome = "ok" | "adminReset" | "signedOut" | "offline";

let inflight: Promise<RefreshOutcome> | null = null;
// Bumped by every sign-in and wipe: a refresh started in an older epoch must not write back
// (it would resurrect a session the user just ended, or overwrite a newer login).
let epoch = 0;

/** Reads the stored refresh token at startup; no network, so a cold start works offline. */
export async function restoreSession(): Promise<void> {
  try {
    // iOS keeps Keychain items after uninstall: a fresh install must not inherit a session.
    await onFreshInstall(() => deleteSecure(...(Object.values(secureKeys) as SecureKey[])));
    // An unacknowledged admin-reset notice survives a restart (docs/04 §1 step 5a).
    if (await readSecure(secureKeys.adminResetNotice)) {
      setStatus("adminReset");
      return;
    }
    const signedIn = Boolean(await readSecure(secureKeys.refresh));
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

/** Stores a fresh login: the refresh token before the session counts as signed in. */
export async function establishSession(pair: TokenResponse): Promise<void> {
  epoch += 1;
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
  const started = epoch;
  let refreshToken: string | null;
  try {
    refreshToken = await readSecure(secureKeys.refresh);
  } catch {
    return "offline"; // Keychain not readable right now (locked phone); try again later
  }
  // Already wiped: keep the current status (e.g. adminReset stays visible to the user).
  if (!refreshToken) return "signedOut";
  let result: Awaited<ReturnType<typeof postRefresh>>;
  try {
    result = await postRefresh(refreshToken);
  } catch {
    return "offline"; // keep the tokens; the next request tries again
  }
  if (started !== epoch) return "signedOut"; // signed out or in again meanwhile
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
    const next = error?.code === "auth.admin_reset" ? "adminReset" : "signedOut";
    await wipeLocal(next);
    return next;
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
 * The trusted-device token stays on a normal sign-out (see `secureKeys.device`); it goes after
 * an admin reset (the server has dropped the trust) or when `forgetDevice` is set.
 * TODO(phase2): also clear the encrypted MMKV cache/queue and scheduled local reminders.
 */
export async function wipeLocal(
  next: "signedOut" | "adminReset",
  { forgetDevice = next === "adminReset" }: { forgetDevice?: boolean } = {},
): Promise<void> {
  epoch += 1;
  clearAccessToken();
  clearPendingActivationToken();
  setBiometricOn(false);
  setLocale("mn"); // the next user starts in the default language
  await queryClient.cancelQueries();
  queryClient.clear();
  try {
    // The biometric choice and unlock key belong to the user who signed out, not the phone.
    const keys = [secureKeys.refresh, secureKeys.biometric, secureKeys.unlockGate];
    await deleteSecure(...(forgetDevice ? [...keys, secureKeys.device] : keys));
    if (next === "adminReset") await writeSecure(secureKeys.adminResetNotice, "1");
  } finally {
    // An admin-reset notice is not replaced by a later, plainer "signed out".
    if (!(next === "signedOut" && getStatus() === "adminReset")) setStatus(next);
    // Only now, with the status no longer signedIn: unlocking any earlier would mount the
    // signed-in screens for a moment (and let them start requests) during the wipe.
    setLocked(false);
  }
}

/** The user has read the admin-reset notice; continue to sign-in. */
export async function acknowledgeAdminReset(): Promise<void> {
  await deleteSecure(secureKeys.adminResetNotice).catch(() => undefined);
  setStatus("signedOut");
}
