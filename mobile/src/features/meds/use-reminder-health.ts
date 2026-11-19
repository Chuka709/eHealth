import { useQuery } from "@tanstack/react-query";
import * as Device from "expo-device";
import * as Notifications from "expo-notifications";
import { useEffect } from "react";
import { AppState, Linking, Platform } from "react-native";

import { localStore } from "@/lib/local-store";
import { queryClient } from "@/lib/query-client";

import { requestReminderSync } from "./reminder-bus";

const key = ["reminder-health"] as const;

export type ReminderHealth = {
  /** notifications are off for the app: no reminder will show (H6) */
  notificationsOff: boolean;
  /** the OS may still ask (first time / iOS provisional) */
  canAsk: boolean;
  /** Android: exact alarms not allowed - reminders can be late, up to about an hour (H18, Q48);
   * null unknown */
  exactOff: boolean | null;
  /** Xiaomi/Redmi/POCO: "Background autostart" (off for new apps; Android cannot tell us) may
   * keep reminders from coming back after a restart - until the user says it is on (R4) */
  autostartHint: boolean;
};

const AUTOSTART_KEY = "reminders.autostart_done.v2";
/** the system build the user confirmed on: an OS update may turn autostart off again (L-4) */
const build = () => Device.osBuildId ?? "unknown";

/** MIUI / HyperOS phones, where the system blocks a new app's start after a reboot. */
export function hasAutostartSetting(): boolean {
  if (Platform.OS !== "android") return false;
  return /xiaomi|redmi|poco/i.test(`${Device.manufacturer ?? ""} ${Device.brand ?? ""}`);
}

/** The phone's "Background autostart" list (MIUI 12-14), else the app's own settings. */
export async function openAutostart(): Promise<void> {
  try {
    await Linking.sendIntent("miui.intent.action.OP_AUTO_START");
  } catch {
    await Linking.openSettings();
  }
}

/** The user turned autostart on: the hint is not shown again until the system is updated. */
export async function confirmAutostart(): Promise<void> {
  (await localStore()).set(AUTOSTART_KEY, build());
  await queryClient.invalidateQueries({ queryKey: key });
}

async function read(): Promise<ReminderHealth> {
  const notifications = await Notifications.getPermissionsAsync();
  let exactOff: boolean | null = false;
  if (Platform.OS === "android") {
    try {
      exactOff = !(await Notifications.getExactAlarmPermissionsAsync()).granted;
    } catch {
      exactOff = null; // unknown: never claimed to be on time
    }
  }
  let autostartHint = false;
  if (hasAutostartSetting()) {
    const done = await localStore()
      .then((s) => s.getString(AUTOSTART_KEY) === build())
      .catch(() => false);
    autostartHint = !done;
  }
  return {
    notificationsOff: !notifications.granted,
    canAsk: notifications.canAskAgain && notifications.status !== "denied",
    exactOff,
    autostartHint,
  };
}

/** Whether reminders can work on this phone; re-read whenever the app comes back. */
export function useReminderHealth() {
  const query = useQuery({ queryKey: key, queryFn: read, networkMode: "always" });
  useEffect(() => {
    const sub = AppState.addEventListener("change", (state) => {
      if (state === "active") void queryClient.invalidateQueries({ queryKey: key });
    });
    return () => sub.remove();
  }, []);
  return query;
}

/** Turn notifications on: the OS prompt when it may still ask, else the app's settings. */
export async function enableNotifications(canAsk: boolean): Promise<void> {
  if (canAsk) {
    await Notifications.requestPermissionsAsync();
  } else {
    await Linking.openSettings();
  }
  await queryClient.invalidateQueries({ queryKey: key });
  requestReminderSync();
}

/** Android: the system's "Alarms & reminders" screen for this app. */
export async function enableExactAlarms(): Promise<void> {
  try {
    await Notifications.requestExactAlarmPermissionsAsync();
  } finally {
    await queryClient.invalidateQueries({ queryKey: key });
    requestReminderSync();
  }
}
