import * as Notifications from "expo-notifications";
import { cancelAllAlarmClocks } from "../../modules/dose-alarm";

/**
 * Sign-out: no reminder of the signed-out user may fire on this phone, and none already shown
 * stays in the notification shade (CLAUDE.md rule 8). Scheduling itself arrives with the
 * medication reminders (Phase 2.5).
 */
export async function clearLocalNotifications(): Promise<void> {
  // Android alarm clocks of dose reminders (Q79); never throws, so the rest always runs
  cancelAllAlarmClocks();
  await Promise.all([
    Notifications.cancelAllScheduledNotificationsAsync(),
    Notifications.dismissAllNotificationsAsync(),
  ]);
}

/**
 * Medicine reminders also show while the app is open (without a handler the OS keeps them
 * silent in the foreground - H6). Registered once, at the app's start.
 */
export function showRemindersInForeground(): void {
  Notifications.setNotificationHandler({
    handleNotification: async () => ({
      shouldShowBanner: true,
      shouldShowList: true,
      shouldPlaySound: true,
      shouldSetBadge: false,
    }),
  });
}
