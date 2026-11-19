import Constants from "expo-constants";
import * as Notifications from "expo-notifications";
import { Platform } from "react-native";

import { api } from "@/lib/api";

/**
 * Server push (Phase 2.8f; docs/08 "Мэдэгдэл"): this device's Expo token goes on this session
 * only (PUT /me/push-token). It is sent again on every start, every return to the foreground
 * and every refresh, so a token another account took over on this phone comes back here by
 * itself (security review 2.8a M4 / 2.8b L5). The token is never logged or stored by the app.
 *
 * Without Expo/FCM/APNs credentials (none yet - decision (c)) no token can be had: the app
 * carries on silently, with local reminders as before.
 */

export const ALERTS_CHANNEL = "alerts";
const MIN_INTERVAL_MS = 60_000; // the server allows 10 a minute per account

let lastSentAt = 0;
let channelReady = false;
let inflight: Promise<PushRegistration> | null = null;

/** Sign-out (and tests): the next account sends its token at once. */
export function resetPushThrottle(): void {
  lastSentAt = 0;
}

/** The EAS project the token belongs to; absent until the app is linked to EAS. */
export function pushProjectId(): string | null {
  const fromConfig = (Constants.expoConfig?.extra as { eas?: { projectId?: unknown } } | undefined)
    ?.eas?.projectId;
  const id = fromConfig ?? Constants.easConfig?.projectId;
  return typeof id === "string" && id.length > 0 ? id : null;
}

/**
 * The Android channel server alerts arrive on: the secure lock screen shows "content hidden"
 * (the text is generic anyway - 2.8b L3); reminders keep their own channel.
 */
export async function registerAlertsChannel(name: string): Promise<void> {
  if (Platform.OS !== "android") {
    channelReady = true;
    return;
  }
  await Notifications.setNotificationChannelAsync(ALERTS_CHANNEL, {
    name,
    importance: Notifications.AndroidImportance.HIGH,
    lockscreenVisibility: Notifications.AndroidNotificationVisibility.PRIVATE,
  });
  channelReady = true;
}

/** For tests: as on a fresh start, before the signed-in screens created the channel. */
export function resetPushChannel(): void {
  channelReady = false;
}

export type PushRegistration = "sent" | "unavailable" | "failed" | "throttled";

/**
 * Sends this device's token for this session. Never asks for permission itself, and never
 * before the alerts channel exists (a push then would show on Android's default channel,
 * whose lock-screen view is not private). One request at a time.
 */
export function registerPushToken(now = Date.now()): Promise<PushRegistration> {
  inflight ??= send(now).finally(() => {
    inflight = null;
  });
  return inflight;
}

async function send(now: number): Promise<PushRegistration> {
  if (!channelReady) return "unavailable";
  if (now - lastSentAt < MIN_INTERVAL_MS) return "throttled";
  const permission = await Notifications.getPermissionsAsync().catch(() => null);
  if (!permission?.granted) return "unavailable";
  const projectId = pushProjectId();
  if (!projectId) return "unavailable";
  let token: string;
  try {
    token = (await Notifications.getExpoPushTokenAsync({ projectId })).data;
  } catch {
    return "unavailable"; // no FCM/APNs credentials, no network, an emulator without Play
  }
  try {
    const { response } = await api.PUT("/api/v1/me/push-token", { body: { token } });
    if (!response.ok) return "failed";
  } catch {
    return "failed";
  }
  lastSentAt = now;
  return "sent";
}

/**
 * Sign-out: this session stops getting pushes on this phone (best effort - offline, the
 * server still drops the session from the queue once it is revoked or expires).
 */
export async function forgetPushToken(): Promise<void> {
  await api.DELETE("/api/v1/me/push-token").catch(() => undefined);
}
