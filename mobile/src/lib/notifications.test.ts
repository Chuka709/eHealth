import * as Notifications from "expo-notifications";

import { clearLocalNotifications } from "./notifications";

const mockCancelAll = jest.fn();
jest.mock("../../modules/dose-alarm", () => ({
  cancelAllAlarmClocks: () => mockCancelAll(),
}));

test("rule 8 / Q79: sign-out cancels the alarm clocks and every scheduled and shown reminder", async () => {
  await clearLocalNotifications();
  expect(mockCancelAll).toHaveBeenCalledTimes(1);
  expect(Notifications.cancelAllScheduledNotificationsAsync).toHaveBeenCalled();
  expect(Notifications.dismissAllNotificationsAsync).toHaveBeenCalled();
});
