import * as Notifications from "expo-notifications";

/**
 * Sign-out: no reminder of the signed-out user may fire on this phone, and none already shown
 * stays in the notification shade (CLAUDE.md rule 8). Scheduling itself arrives with the
 * medication reminders (Phase 2.5).
 */
export async function clearLocalNotifications(): Promise<void> {
  await Promise.all([
    Notifications.cancelAllScheduledNotificationsAsync(),
    Notifications.dismissAllNotificationsAsync(),
  ]);
}
