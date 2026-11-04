import { radius, space } from "@labtrack/shared";
import { StyleSheet, View } from "react-native";
import { useTranslations } from "use-intl";

import { Button } from "@/components/button";
import { FormMessage } from "@/components/form-message";
import { Paragraph } from "@/components/text";
import { formatDateTime } from "@/lib/dates";
import { useErrorText } from "@/lib/use-error-text";
import { usePalette } from "@/theme/use-palette";

import { useAdminNotices, useMarkNoticeRead } from "./use-account";
import { useReportFlow } from "./use-report-flow";

const KNOWN_TITLES = new Set(["account.admin_reset", "account.identity_set"]);
const REPORT_WINDOW_MS = 30 * 86_400_000;

/**
 * Home banner for unread admin changes (docs/04 §1 step 5c): after a reset the new holder of the
 * account may be the attacker, so the real owner — on any device — sees what was done and can
 * lock the account with "Би хүсээгүй".
 */
export function AdminNoticeBanner() {
  const t = useTranslations("app");
  const p = usePalette();
  const errorText = useErrorText();
  const notices = useAdminNotices();
  const markRead = useMarkNoticeRead();
  const { confirm, report, noRecent } = useReportFlow();
  if (!notices.data || notices.data.length === 0) return null;

  const label = (key: string) =>
    KNOWN_TITLES.has(key) ? t(`notification.${key}`) : t("notification.unknown");
  // The server accepts a report only within 30 days of an admin action (0007).
  const reportable = notices.data.some(
    (notice) => Date.now() - Date.parse(notice.created_at) < REPORT_WINDOW_MS,
  );
  return (
    <View style={[styles.box, { borderColor: p.feedback.warning.fg, backgroundColor: p.surface }]}>
      <FormMessage kind="warning" text={t("notification.banner")} />
      {notices.data.map((notice) => (
        <Paragraph key={notice.id}>
          {t("notification.when", {
            what: label(notice.title_key),
            date: formatDateTime(notice.created_at),
          })}
        </Paragraph>
      ))}
      <Paragraph muted>{t("notification.ifNotYou")}</Paragraph>
      {noRecent && <FormMessage kind="error" text={t("adminHistory.noRecent")} />}
      {report.isError && !noRecent && <FormMessage kind="error" text={errorText(report.error)} />}
      {markRead.isError && <FormMessage kind="error" text={errorText(markRead.error)} />}
      <Button
        variant="secondary"
        label={t("notification.wasMe")}
        busy={markRead.isPending}
        onPress={() => markRead.mutate(notices.data.map((notice) => notice.id))}
      />
      {reportable && (
        <View style={styles.apart}>
          <Button
            variant="danger"
            label={t("adminHistory.report")}
            accessibilityLabel={t("adminHistory.reportLabel")}
            busy={report.isPending}
            onPress={confirm}
          />
        </View>
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  box: {
    gap: space.sm,
    padding: space.md,
    borderRadius: radius.md,
    borderWidth: space.xs / 2,
  },
  // Kept apart from "this was my request" so the two are not pressed by mistake.
  apart: { marginTop: space.md },
});
