import { useQuery } from "@tanstack/react-query";
import * as Notifications from "expo-notifications";
import { useEffect } from "react";
import { AppState, Linking, Platform } from "react-native";

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
};

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
  return {
    notificationsOff: !notifications.granted,
    canAsk: notifications.canAskAgain && notifications.status !== "denied",
    exactOff,
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
