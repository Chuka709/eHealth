import { feedbackGlyph, fontSize, radius, space } from "@labtrack/shared";
import { useLocalSearchParams } from "expo-router";
import { StyleSheet, View } from "react-native";
import { useTranslations } from "use-intl";

import { Text } from "@/components/app-text";
import { FormMessage } from "@/components/form-message";
import { Screen } from "@/components/screen";
import { LoadingView, RetryView } from "@/components/state-view";
import { Paragraph, Title } from "@/components/text";
import { useRecordProfile } from "@/features/health/record-screens";
import {
  knownIssues,
  type LabReport,
  type LabResult,
  useDocumentReports,
} from "@/features/upload/use-reports";
import { formatDate, formatDateTime } from "@/lib/dates";
import { useErrorText } from "@/lib/use-error-text";
import { usePalette } from "@/theme/use-palette";

/**
 * What was read from one document (Phase 4.6), read-only: each row as printed (name, value,
 * unit, range) so it can be held against the paper, with what needs checking. A draft (rule 4):
 * no flag and no judgement here; confirming and editing come with the review screen (Phase 5).
 */
export default function DocumentReportsScreen() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const t = useTranslations("app.upload.review");
  const errorText = useErrorText();
  const tu = useTranslations("app.upload");
  const { patients, own } = useRecordProfile();
  const reports = useDocumentReports(own?.id, id);

  if (!own && !patients.isPending) {
    return (
      <Screen>
        <Paragraph>{tu("noProfile")}</Paragraph>
      </Screen>
    );
  }
  if (reports.isPending) return <LoadingView />;
  if (!reports.data) {
    return <RetryView text={errorText(reports.error)} onRetry={() => void reports.refetch()} />;
  }
  const drafts = reports.data.filter((r) => r.status === "needs_review");
  const byAi = reports.data.some((r) => r.method === "ai");
  const anyIssue = (code: string) =>
    reports.data.some((r) => r.results.some((x) => x.issues.includes(code)));
  const nameMismatch = anyIssue("name_mismatch");
  const nameMissing = !nameMismatch && anyIssue("name_missing");
  return (
    <Screen testID="document-reports">
      <Title>{t("title")}</Title>
      {drafts.length > 0 && <FormMessage kind="warning" quiet text={t("draftNotice")} />}
      {byAi && <FormMessage kind="warning" quiet text={t("byAi")} />}
      {nameMismatch && <FormMessage kind="error" quiet text={t("nameMismatch")} />}
      {nameMissing && <FormMessage kind="warning" quiet text={t("nameMissing")} />}
      {reports.data.length === 0 ? (
        <Paragraph>{t("empty")}</Paragraph>
      ) : (
        reports.data.map((r) => <ReportCard key={r.id} report={r} />)
      )}
      {drafts.length > 0 && <Paragraph muted>{t("comingSoon")}</Paragraph>}
    </Screen>
  );
}

const DOCUMENT_ISSUES = new Set<string>(["name_mismatch", "name_missing"]);

function collectedText(report: LabReport): string | null {
  if (!report.collected_at) return null;
  return report.collected_precision === "day"
    ? formatDate(report.collected_at)
    : formatDateTime(report.collected_at);
}

function ReportCard({ report }: { report: LabReport }) {
  const t = useTranslations("app.upload.review");
  const p = usePalette();
  const collected = collectedText(report);
  const meta = [report.lab_name, report.specimen].filter(Boolean).join(" · ");
  return (
    <View style={styles.section}>
      <Text accessibilityRole="header" style={[styles.heading, { color: p.text }]}>
        {report.panel_name ?? report.lab_name ?? t("untitled")}
      </Text>
      {report.status === "needs_review" && (
        <Text style={[styles.meta, styles.draft, { color: p.feedback.warning.fg }]}>
          {`${feedbackGlyph.warning} ${t("draftLabel")}`}
        </Text>
      )}
      {meta.length > 0 && <Text style={[styles.meta, { color: p.textMuted }]}>{meta}</Text>}
      <Text style={[styles.meta, { color: p.textMuted }]}>
        {collected ? t("collected", { date: collected }) : t("dateUnknown")}
      </Text>
      <View style={[styles.card, { backgroundColor: p.surface, borderColor: p.border }]}>
        {report.results.map((x, i) => (
          <ResultRow key={x.id} result={x} first={i === 0} />
        ))}
      </View>
    </View>
  );
}

function ResultRow({ result, first }: { result: LabResult; first: boolean }) {
  const t = useTranslations("app.upload.review");
  const p = usePalette();
  // the name is the document's, said once in the banner above - not on every row
  const issues = knownIssues(result.issues).filter((i) => !DOCUMENT_ISSUES.has(i));
  const value = [result.raw_value, result.raw_unit].filter(Boolean).join(" ");
  const range = result.ref_text ? t("range", { range: result.ref_text }) : t("noRange");
  // a critical limit as printed on the document, if any (rule 5: never one of ours)
  const critical = result.critical_text ? t("critical", { range: result.critical_text }) : null;
  const known =
    result.test_name_mn && result.test_name_mn !== result.raw_name ? result.test_name_mn : null;
  const issueText = issues.map((i) => t(`issues.${i}`)).join(", ");
  return (
    <View
      accessible
      accessibilityRole="text"
      accessibilityLabel={[
        result.raw_name,
        value,
        range,
        critical,
        issueText && `${t("check")}: ${issueText}`,
      ]
        .filter(Boolean)
        .join(". ")}
      style={[
        styles.row,
        !first && { borderTopColor: p.border, borderTopWidth: StyleSheet.hairlineWidth },
      ]}
      testID={`result-${result.position}`}
    >
      <View style={styles.line}>
        <Text style={[styles.name, { color: p.text }]}>{result.raw_name}</Text>
        <Text style={[styles.value, { color: p.text }]}>{value}</Text>
      </View>
      {known && <Text style={[styles.meta, { color: p.textMuted }]}>{known}</Text>}
      <Text style={[styles.meta, { color: p.textMuted }]}>{range}</Text>
      {critical && <Text style={[styles.meta, { color: p.textMuted }]}>{critical}</Text>}
      {issues.length > 0 && (
        <Text style={[styles.meta, { color: p.feedback.warning.fg }]}>
          {`${feedbackGlyph.warning} ${t("check")}: ${issueText}`}
        </Text>
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  section: { gap: space.xs },
  heading: { fontSize: fontSize.body, fontWeight: "700" },
  card: {
    marginTop: space.sm,
    borderRadius: radius.lg,
    borderWidth: StyleSheet.hairlineWidth,
    overflow: "hidden",
  },
  row: { paddingHorizontal: space.lg, paddingVertical: space.md, gap: 2 },
  line: { flexDirection: "row", flexWrap: "wrap", justifyContent: "space-between", gap: space.sm },
  name: { fontSize: fontSize.body, fontWeight: "600", flexShrink: 1 },
  value: { fontSize: fontSize.body, fontVariant: ["tabular-nums"] },
  meta: { fontSize: fontSize.caption },
  draft: { fontWeight: "600" },
});
