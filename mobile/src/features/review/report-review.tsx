import { type Flag, feedbackGlyph, flagGlyph, fontSize, radius, space } from "@labtrack/shared";
import { useRouter } from "expo-router";
import { useState } from "react";
import { Alert, Linking, StyleSheet, View } from "react-native";
import { useTranslations } from "use-intl";

import { Text } from "@/components/app-text";
import { Button } from "@/components/button";
import { Choices } from "@/components/choices";
import { PickerField } from "@/components/date-field";
import { FormMessage } from "@/components/form-message";
import { knownIssues, type LabReport, type LabResult } from "@/features/upload/use-reports";
import { formatDate, formatDateTime } from "@/lib/dates";
import { useErrorText } from "@/lib/use-error-text";
import { usePalette } from "@/theme/use-palette";

import { localMoment } from "./moments";
import { useReviewActions } from "./use-review";

/**
 * One lab report under review (docs/06 §4, docs/08 "Хянах"; Phase 5.5). What the app shows is
 * what the server computed (rule 6): the row as printed, the flag against the printed range,
 * the issues to look at. Each issue is looked at on its own ("Хэвлэснээрээ зөв"); a missing,
 * ambiguous or future date is never accepted - it is picked from the result; the name is
 * confirmed for the whole report. Rows that may be critical come first, under a red banner
 * (H5); "Батлах" stays off until nothing is left to check. Nothing here suggests a value.
 */

// on every row, but about the report: shown once, above the rows
const REPORT_ISSUES = new Set(["name_mismatch", "name_missing", "date_old", "date_inconsistent"]);
const DATE_TO_PICK = new Set(["date_missing", "date_ambiguous", "date_future"]);
const CRITICAL_FLAGS = new Set(["critical_low", "critical_high"]);

export function isCritical(row: LabResult): boolean {
  return (
    CRITICAL_FLAGS.has(row.flag) ||
    row.issues.includes("possible_critical") ||
    (row.issues.includes("critical_edited") && !row.acknowledged.includes("critical_edited"))
  );
}

function openIssues(row: LabResult): string[] {
  return row.issues.filter((i) => !row.acknowledged.includes(i));
}

const ABOUT_REPORT = (i: string) => REPORT_ISSUES.has(i) || DATE_TO_PICK.has(i);

/** What is left to check: rows with an issue of their own, plus each report-level one once
 * (a name or date issue sits on every row but is one thing to do). */
export function openRowCount(report: LabReport): number {
  const rows = report.results.filter((r) => openIssues(r).some((i) => !ABOUT_REPORT(i)));
  const about = new Set(
    report.results
      .flatMap(openIssues)
      .filter(ABOUT_REPORT)
      .map((i) => (i.startsWith("name_") ? "name" : DATE_TO_PICK.has(i) ? "date" : i)),
  );
  return rows.length + about.size;
}

const FLAGS = new Set([
  "normal",
  "low",
  "high",
  "critical_low",
  "critical_high",
  "abnormal",
  "no_reference",
  "unknown",
]);
// accepted as matching the printout, but still about a possibly critical value: not "✓"
const STILL_CRITICAL = new Set(["possible_critical", "critical_edited"]);

function flagToken(flag: string): Flag {
  if (CRITICAL_FLAGS.has(flag)) return "critical";
  if (flag === "normal" || flag === "low" || flag === "high" || flag === "abnormal") return flag;
  return "no_reference";
}

function collectedText(report: LabReport): string | null {
  if (!report.collected_at) return null;
  return report.collected_precision === "day"
    ? formatDate(report.collected_at)
    : formatDateTime(report.collected_at);
}

function sorted(rows: LabResult[]): LabResult[] {
  const rank = (r: LabResult) => (isCritical(r) ? 0 : openIssues(r).length > 0 ? 1 : 2);
  return [...rows].sort((a, b) => rank(a) - rank(b) || a.position - b.position);
}

export function ReportReview({
  patientId,
  profileName,
  report,
  onMove,
}: {
  patientId: string;
  profileName: string;
  report: LabReport;
  /** "Wrong profile": offered for a document's drafts (the owner moves it - 0037). */
  onMove?: () => void;
}) {
  const t = useTranslations("app.upload.review");
  const p = usePalette();
  const router = useRouter();
  const errorText = useErrorText();
  const actions = useReviewActions(patientId, report.id);
  const draft = report.status === "needs_review";
  const allIssues = new Set(report.results.flatMap(openIssues));
  const nameIssue = ["name_mismatch", "name_missing"].find((i) => allIssues.has(i));
  const reportIssues = [...allIssues].filter((i) => REPORT_ISSUES.has(i) && i !== nameIssue);
  const pickDate = [...allIssues].some((i) => DATE_TO_PICK.has(i));
  const open = openRowCount(report);
  const busy =
    actions.confirm.isPending || actions.reject.isPending || actions.editReport.isPending;
  const failure = [
    actions.confirm,
    actions.reject,
    actions.editReport,
    actions.editResult,
    actions.deleteResult,
  ]
    .map((m) => m.error)
    .find(Boolean);
  const collected = collectedText(report);

  const reject = () => {
    const critical = report.has_unconfirmed_critical;
    Alert.alert(t("reject"), critical ? t("rejectCritical") : t("rejectConfirm"), [
      { text: t("cancel"), style: "cancel" },
      {
        text: t("reject"),
        style: "destructive",
        onPress: () => actions.reject.mutate(critical),
      },
    ]);
  };

  return (
    <View style={styles.section} testID={`report-${report.id}`}>
      <Text accessibilityRole="header" style={[styles.heading, { color: p.text }]}>
        {report.panel_name ?? report.lab_name ?? t("untitled")}
      </Text>
      <Text style={[styles.meta, styles.strong, { color: p.textMuted }]}>
        {report.status === "confirmed"
          ? t("confirmed")
          : report.status === "rejected"
            ? t("rejected")
            : t("draftLabel")}
        {report.source === "typed" ? ` · ${t("typed")}` : ""}
      </Text>
      <Text style={[styles.meta, { color: p.textMuted }]}>
        {collected ? t("collected", { date: collected }) : t("dateUnknown")}
      </Text>

      {draft && report.has_unconfirmed_critical && (
        <View
          accessibilityRole="alert"
          style={[styles.banner, { backgroundColor: p.flag.critical.bg }]}
          testID="critical-banner"
        >
          <Text style={[styles.bannerText, { color: p.flag.critical.fg }]}>
            {`${flagGlyph.critical} ${t("criticalBanner")}`}
          </Text>
        </View>
      )}
      {draft && report.has_unconfirmed_critical && (
        // outside the red banner: a plain button keeps its contrast (AA)
        <Button
          label={t("call103")}
          variant="secondary"
          onPress={() =>
            // a phone that cannot call (a tablet): the number, at least
            void Linking.openURL("tel:103").catch(() => Alert.alert(t("call103"), "103"))
          }
        />
      )}
      {failure && <FormMessage kind="error" text={errorText(failure)} />}

      {draft && pickDate && (
        <DateEditor
          busy={actions.editReport.isPending}
          onSave={(at, precision) =>
            actions.editReport.mutate({ collected_at: at, collected_precision: precision })
          }
        />
      )}

      {draft && nameIssue && (
        <View style={[styles.box, { borderColor: p.border, backgroundColor: p.surface }]}>
          <FormMessage
            kind={nameIssue === "name_mismatch" ? "error" : "warning"}
            quiet
            text={nameIssue === "name_mismatch" ? t("nameMismatch") : t("nameMissing")}
          />
          <Button
            label={t("nameConfirm", { name: profileName })}
            variant="secondary"
            busy={actions.editReport.isPending}
            onPress={() => actions.editReport.mutate({ acknowledge: [nameIssue] })}
          />
          {onMove && <Button label={t("wrongProfile")} variant="link" onPress={onMove} />}
        </View>
      )}

      {draft &&
        reportIssues.map((issue) => (
          <View key={issue} style={styles.issueLine}>
            <Text style={[styles.issue, { color: p.feedback.warning.fg, flexShrink: 1 }]}>
              {`${feedbackGlyph.warning} ${t(`issues.${knownIssues([issue])[0]}`)}`}
            </Text>
            <Button
              label={t("matches")}
              compact
              variant="secondary"
              accessibilityLabel={t("matchesLabel", {
                issue: t(`issues.${knownIssues([issue])[0]}`),
              })}
              onPress={() => actions.editReport.mutate({ acknowledge: [issue] })}
            />
          </View>
        ))}

      <View style={[styles.card, { backgroundColor: p.surface, borderColor: p.border }]}>
        {sorted(report.results).map((row, i) => (
          <ResultCard
            key={row.id}
            row={row}
            first={i === 0}
            draft={draft}
            lastDoses={report.last_doses.filter((d) => d.test_code === row.test_code)}
            onAccept={(issue) =>
              actions.editResult.mutate({ resultId: row.id, patch: { acknowledge: [issue] } })
            }
            onEdit={() =>
              router.push({
                pathname: "/results/row",
                params: { report: report.id, row: row.id },
              })
            }
            onDelete={() => {
              const critical = isCritical(row);
              Alert.alert(t("deleteRow"), critical ? t("deleteCritical") : t("deleteConfirm"), [
                { text: t("cancel"), style: "cancel" },
                {
                  text: t("deleteRow"),
                  style: "destructive",
                  onPress: () =>
                    actions.deleteResult.mutate({ resultId: row.id, criticalSeen: critical }),
                },
              ]);
            }}
          />
        ))}
      </View>

      {draft && (
        <View style={styles.footer}>
          <Button
            label={t("addRow")}
            variant="secondary"
            onPress={() => router.push({ pathname: "/results/row", params: { report: report.id } })}
          />
          <Text
            style={[styles.issue, { color: open > 0 ? p.feedback.warning.fg : p.textMuted }]}
            testID="open-count"
          >
            {t("openCount", { count: open })}
          </Text>
          <Button
            label={t("confirm")}
            disabled={open > 0 || !report.collected_at || busy}
            busy={actions.confirm.isPending}
            onPress={() => actions.confirm.mutate()}
            accessibilityLabel={`${t("confirm")}. ${t("openCount", { count: open })}`}
          />
          {!report.collected_at && (
            <Text style={[styles.issue, { color: p.feedback.warning.fg }]}>{t("dateNeeded")}</Text>
          )}
          <Text style={[styles.meta, { color: p.textMuted }]}>{t("confirmHint")}</Text>
          <Button label={t("reject")} variant="link" onPress={reject} />
        </View>
      )}
    </View>
  );
}

function DateEditor({
  busy,
  onSave,
}: {
  busy: boolean;
  onSave: (at: string, precision: "day" | "minute") => void;
}) {
  const t = useTranslations("app.upload.review");
  const p = usePalette();
  const [precision, setPrecision] = useState<"day" | "minute" | null>(null);
  const [day, setDay] = useState<string | null>(null);
  const [time, setTime] = useState<string | null>(null);
  const ready = day !== null && precision !== null && (precision === "day" || time !== null);
  return (
    <View
      style={[styles.box, { borderColor: p.border, backgroundColor: p.surface }]}
      testID="date-editor"
    >
      <Text style={[styles.strong, { color: p.text }]}>{t("dateTitle")}</Text>
      <Text style={[styles.meta, { color: p.feedback.warning.fg }]}>{t("dateNeeded")}</Text>
      <PickerField
        label={t("date")}
        mode="date"
        value={day}
        maximum={new Date()}
        onChange={setDay}
      />
      <Choices
        label={t("precision")}
        options={["day", "minute"] as const}
        value={precision}
        labelOf={(o) => (o === "day" ? t("precisionDay") : t("precisionMinute"))}
        onSelect={setPrecision}
      />
      {precision === "minute" && (
        <PickerField label={t("time")} mode="time" value={time} onChange={setTime} />
      )}
      <Button
        label={t("saveDate")}
        disabled={!ready}
        busy={busy}
        onPress={() => {
          if (!ready || day === null || precision === null) return;
          onSave(localMoment(day, precision === "minute" ? time : null), precision);
        }}
      />
    </View>
  );
}

function ResultCard({
  row,
  first,
  draft,
  lastDoses,
  onAccept,
  onEdit,
  onDelete,
}: {
  row: LabResult;
  first: boolean;
  draft: boolean;
  lastDoses: LabReport["last_doses"];
  onAccept: (issue: string) => void;
  onEdit: () => void;
  onDelete: () => void;
}) {
  const t = useTranslations("app.upload.review");
  const p = usePalette();
  const token = flagToken(row.flag);
  const colour = p.flag[token];
  const value = [row.raw_value, row.raw_unit].filter(Boolean).join(" ");
  const range = row.ref_text ? t("range", { range: row.ref_text }) : t("noRange");
  const critical = row.critical_text ? t("critical", { range: row.critical_text }) : null;
  const known = row.test_name_mn && row.test_name_mn !== row.raw_name ? row.test_name_mn : null;
  const open = openIssues(row).filter((i) => !REPORT_ISSUES.has(i) && !DATE_TO_PICK.has(i));
  const accepted = row.acknowledged.filter((i) => !REPORT_ISSUES.has(i));
  const stillCritical = row.acknowledged.filter((i) => STILL_CRITICAL.has(i));
  const flagText = t(`flags.${FLAGS.has(row.flag) ? row.flag : "unknown"}` as "flags.unknown");
  // the server's flag may be "within range" while a critical limit could not be told (L1)
  const possiblyCritical = row.issues.includes("possible_critical");
  const doseTexts = lastDoses.map((d) =>
    [
      d.time_unknown || d.taken_at === null || d.minutes_before === null
        ? t("lastDoseUnknown", { medicine: d.medication_name })
        : t("lastDose", {
            medicine: d.medication_name,
            time: formatDateTime(d.taken_at),
            hours: Math.floor(d.minutes_before / 60),
            minutes: d.minutes_before % 60,
          }),
      d.other_records > 0 ? t("lastDoseExtra", { count: d.other_records }) : null,
    ]
      .filter(Boolean)
      .join(" · "),
  );
  const acceptedText =
    accepted.length > 0
      ? `${t("accepted")}: ${accepted.map((i) => t(`issues.${knownIssues([i])[0]}`)).join(", ")}`
      : null;
  return (
    <View
      style={[
        styles.row,
        !first && { borderTopColor: p.border, borderTopWidth: StyleSheet.hairlineWidth },
      ]}
      testID={`result-${row.position}`}
    >
      <View
        accessible
        accessibilityRole="text"
        accessibilityLabel={[
          row.raw_name,
          value,
          flagText,
          possiblyCritical ? t("possibleCritical") : null,
          range,
          critical,
          row.read_value ? t("correctedFrom", { value: row.read_value }) : null,
          ...doseTexts,
          acceptedText,
        ]
          .filter(Boolean)
          .join(". ")}
        style={styles.rowText}
      >
        <View style={styles.line}>
          <Text style={[styles.name, { color: p.text }]}>{row.raw_name}</Text>
          <Text style={[styles.value, { color: p.text }]}>{value}</Text>
        </View>
        {known && <Text style={[styles.meta, { color: p.textMuted }]}>{known}</Text>}
        <View style={styles.chips}>
          <View style={[styles.flag, { backgroundColor: colour.bg }]}>
            <Text style={[styles.meta, styles.strong, { color: colour.fg }]}>
              {`${flagGlyph[token]} ${flagText}`}
            </Text>
          </View>
          {possiblyCritical && token !== "critical" && (
            <View style={[styles.flag, { backgroundColor: p.flag.critical.bg }]}>
              <Text style={[styles.meta, styles.strong, { color: p.flag.critical.fg }]}>
                {`${flagGlyph.critical} ${t("possibleCritical")}`}
              </Text>
            </View>
          )}
        </View>
        <Text style={[styles.meta, { color: p.textMuted }]}>{range}</Text>
        {critical && <Text style={[styles.meta, { color: p.textMuted }]}>{critical}</Text>}
        {row.read_value && (
          <Text style={[styles.meta, { color: p.textMuted }]}>
            {t("correctedFrom", { value: row.read_value })}
          </Text>
        )}
        {doseTexts.map((text, i) => (
          <Text
            key={lastDoses[i]?.medication_id ?? i}
            style={[styles.meta, { color: p.textMuted }]}
          >
            {text}
          </Text>
        ))}
        {acceptedText && (
          <Text style={[styles.meta, { color: p.textMuted }]}>
            {/* accepted but still about a possibly critical value: no "done" mark */}
            {stillCritical.length > 0 ? acceptedText : `${feedbackGlyph.success} ${acceptedText}`}
          </Text>
        )}
      </View>
      {draft &&
        open.map((issue) => (
          <View key={issue} style={styles.issueLine}>
            <Text style={[styles.issue, { color: p.feedback.warning.fg, flexShrink: 1 }]}>
              {`${feedbackGlyph.warning} ${t(`issues.${knownIssues([issue])[0]}`)}`}
            </Text>
            <Button
              label={t("matches")}
              compact
              variant="secondary"
              accessibilityLabel={t("matchesLabel", {
                issue: t(`issues.${knownIssues([issue])[0]}`),
              })}
              onPress={() => onAccept(issue)}
            />
          </View>
        ))}
      {draft && (
        <View style={styles.actions}>
          <Button label={t("edit")} compact variant="secondary" onPress={onEdit} />
          <Button label={t("deleteRow")} compact variant="quiet" onPress={onDelete} />
        </View>
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  section: { gap: space.sm },
  heading: { fontSize: fontSize.bodyLarge, fontWeight: "700" },
  meta: { fontSize: fontSize.caption },
  issue: { fontSize: fontSize.body },
  chips: { flexDirection: "row", flexWrap: "wrap", gap: space.xs },
  strong: { fontWeight: "600" },
  banner: { borderRadius: radius.md, padding: space.md, gap: space.sm },
  bannerText: { fontSize: fontSize.body, fontWeight: "700" },
  box: {
    borderRadius: radius.md,
    borderWidth: StyleSheet.hairlineWidth,
    padding: space.md,
    gap: space.sm,
  },
  card: {
    borderRadius: radius.lg,
    borderWidth: StyleSheet.hairlineWidth,
    overflow: "hidden",
  },
  row: { paddingHorizontal: space.lg, paddingVertical: space.md, gap: space.xs },
  rowText: { gap: space.xs },
  line: { flexDirection: "row", flexWrap: "wrap", justifyContent: "space-between", gap: space.sm },
  name: { fontSize: fontSize.body, fontWeight: "600", flexShrink: 1 },
  value: { fontSize: fontSize.body, fontVariant: ["tabular-nums"] },
  flag: {
    alignSelf: "flex-start",
    borderRadius: radius.sm,
    paddingHorizontal: space.sm,
    paddingVertical: space.xs,
  },
  issueLine: {
    flexDirection: "row",
    flexWrap: "wrap",
    alignItems: "center",
    justifyContent: "space-between",
    gap: space.sm,
  },
  actions: { flexDirection: "row", flexWrap: "wrap", gap: space.sm },
  footer: { gap: space.sm, marginTop: space.sm },
});
