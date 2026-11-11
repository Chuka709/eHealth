import { fontSize, radius, space } from "@labtrack/shared";
import { StyleSheet, View } from "react-native";
import { useTranslations } from "use-intl";
import { Text } from "@/components/app-text";

import { Button } from "@/components/button";
import { FormMessage } from "@/components/form-message";
import { Screen } from "@/components/screen";
import { LoadingView, RetryView } from "@/components/state-view";
import { Paragraph } from "@/components/text";
import { useAdminActions } from "@/features/me/use-account";
import { useReportFlow } from "@/features/me/use-report-flow";
import { formatDateTime } from "@/lib/dates";
import { useErrorText } from "@/lib/use-error-text";
import { usePalette } from "@/theme/use-palette";

// Only labels we wrote; anything else (a new server action) reads "Other admin action".
const KNOWN_ACTIONS = new Set([
  "user_create",
  "token_issue",
  "identity_check",
  "identity_set",
  "phone_reveal",
  "sms_target",
  "status_active",
  "status_locked",
  "status_disabled",
  "lockout_clear",
  "deletion_cancel",
]);

export default function AdminHistoryScreen() {
  const t = useTranslations("app");
  const p = usePalette();
  const errorText = useErrorText();
  const actions = useAdminActions();
  const { confirm, report, noRecent } = useReportFlow();

  if (actions.isPending) return <LoadingView />;
  if (!actions.data) {
    return <RetryView text={errorText(actions.error)} onRetry={() => void actions.refetch()} />;
  }
  const what = (action: string) => {
    const name = action.replace(/^admin\./, "");
    return KNOWN_ACTIONS.has(name) ? t(`adminAction.${name}`) : t("adminAction.unknown");
  };
  const role = (value: string | null) => {
    const key = `adminHistory.role.${value ?? "unknown"}`;
    return t.has(key) ? t(key) : t("adminHistory.role.unknown");
  };

  return (
    <Screen>
      <Paragraph>{t("adminHistory.intro")}</Paragraph>
      {actions.data.length === 0 && <Paragraph muted>{t("adminHistory.none")}</Paragraph>}
      {actions.data.map((entry) => (
        <View
          key={`${entry.at}-${entry.action}-${entry.actor_role ?? ""}`}
          accessible
          style={[styles.row, { backgroundColor: p.surface, borderColor: p.border }]}
        >
          <Text style={[styles.what, { color: p.text }]}>{what(entry.action)}</Text>
          <Paragraph muted>
            {t("adminHistory.whenWho", {
              date: formatDateTime(entry.at),
              role: role(entry.actor_role),
            })}
          </Paragraph>
        </View>
      ))}
      <Paragraph muted>{t("adminHistory.reportHint")}</Paragraph>
      {noRecent && <FormMessage kind="error" text={t("adminHistory.noRecent")} />}
      {report.isError && !noRecent && <FormMessage kind="error" text={errorText(report.error)} />}
      <Button
        variant="danger"
        label={t("adminHistory.report")}
        accessibilityLabel={t("adminHistory.reportLabel")}
        busy={report.isPending}
        onPress={confirm}
      />
    </Screen>
  );
}

const styles = StyleSheet.create({
  row: {
    gap: space.xs,
    padding: space.md,
    borderRadius: radius.md,
    borderWidth: StyleSheet.hairlineWidth * 2,
  },
  what: { fontSize: fontSize.body, fontWeight: "600" },
});
