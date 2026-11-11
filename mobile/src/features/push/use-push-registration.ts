import * as Notifications from "expo-notifications";
import { useEffect } from "react";
import { AppState } from "react-native";
import { useTranslations } from "use-intl";

import { refreshNotices } from "@/features/notices/use-notifications";

import { registerAlertsChannel, registerPushToken } from "./push-token";

/**
 * Signed in and unlocked ((main) layout): the alerts channel and this device's push token, at
 * the start and every time the app comes back to the foreground. Failures are silent: without
 * push the app works as before (local reminders, the in-app list of notifications).
 */
export function usePushRegistration(): void {
  const t = useTranslations("app.notifications");
  const channel = t("channel");
  useEffect(() => {
    const register = () => {
      void registerAlertsChannel(channel)
        .then(() => registerPushToken())
        .catch(() => undefined);
    };
    register();
    const sub = AppState.addEventListener("change", (state) => {
      if (state === "active") register();
    });
    // a push while the app is open: the 🔔 count follows at once
    const received = Notifications.addNotificationReceivedListener((n) => {
      const trigger = n.request.trigger as { type?: string } | null;
      if (trigger?.type === "push") void refreshNotices().catch(() => undefined);
    });
    return () => {
      sub.remove();
      received.remove();
    };
  }, [channel]);
}
