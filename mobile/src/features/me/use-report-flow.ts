import { Alert } from "react-native";
import { useTranslations } from "use-intl";

import { ApiError } from "@/lib/use-error-text";

import { useReportUnwantedAdminAction } from "./use-account";

/** "Би хүсээгүй" with its confirmation; `noRecent` when there was no admin action in 30 days. */
export function useReportFlow() {
  const t = useTranslations("app");
  const report = useReportUnwantedAdminAction();
  const confirm = () =>
    Alert.alert(
      t("adminHistory.reportTitle"),
      t("adminHistory.reportBody"),
      [
        { text: t("common.cancel"), style: "cancel" },
        {
          text: t("adminHistory.reportConfirm"),
          style: "destructive",
          onPress: () => report.mutate(),
        },
      ],
      { cancelable: true },
    );
  const noRecent =
    report.error instanceof ApiError && report.error.code === "me.no_recent_admin_action";
  return { confirm, report, noRecent };
}
