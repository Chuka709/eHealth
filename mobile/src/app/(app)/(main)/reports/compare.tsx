import { flagGlyph, fontSize, radius, space } from "@labtrack/shared";
import { useLocalSearchParams } from "expo-router";
import { StyleSheet, useWindowDimensions, View } from "react-native";
import { useTranslations } from "use-intl";

import { Text } from "@/components/app-text";
import { Screen } from "@/components/screen";
import { LoadingView, RetryView } from "@/components/state-view";
import { Paragraph } from "@/components/text";
import { useRecordProfile } from "@/features/health/record-screens";
import { flagKey, flagToken } from "@/features/review/flag";
import { useReport } from "@/features/review/use-review";
import type { LabReport, LabResult } from "@/features/upload/use-reports";
import { formatDate } from "@/lib/dates";
import { useErrorText } from "@/lib/use-error-text";
import { usePalette } from "@/theme/use-palette";

/**
 * Two confirmed reports side by side (docs/06 §5 "Харьцуулах"; Phase 6.9): each test once, with
 * its value, flag and range as EACH result printed them - another lab may print another range,
 * so nothing is subtracted or compared here (rule 5, 6). The older report comes first.
 */
export default function CompareReports() {
  const { a, b } = useLocalSearchParams<{ a: string; b: string }>();
  const t = useTranslations("app.timeline.compareScreen");
  const errorText = useErrorText();
  const { own } = useRecordProfile();
  // large text: the two results one under the other, not two narrow columns
  const stacked = useWindowDimensions().fontScale > 1.3;
  const ra = useReport(own?.id, a);
  const rb = useReport(own?.id, b);
  if (!own || ra.isPending || rb.isPending) return <LoadingView />;
  if (!ra.data || !rb.data) {
    return (
      <RetryView
        text={errorText(ra.error ?? rb.error)}
        onRetry={() => {
          void ra.refetch();
          void rb.refetch();
        }}
      />
    );
  }
  if (ra.data.status !== "confirmed" || rb.data.status !== "confirmed") {
    return (
      <Screen>
        <Paragraph>{t("notConfirmed")}</Paragraph>
      </Screen>
    );
  }
  const [first, second] = [ra.data, rb.data].sort((x, y) =>
    (x.collected_at ?? "").localeCompare(y.collected_at ?? ""),
  );
  const rows = joinRows(first, second);
  const dateOf = (r: LabReport) => (r.collected_at ? formatDate(r.collected_at) : t("noDate"));
  return (
    <Screen testID="compare-screen">
      <Paragraph muted>{t("note")}</Paragraph>
      {!stacked && (
        <View style={styles.heads}>
          <Head report={first} />
          <Head report={second} />
        </View>
      )}
      {rows.map((r) => (
        <View key={r.key} style={styles.block} testID={`cmp-${r.key}`}>
          <Text style={styles.name}>{r.name}</Text>
          <View style={stacked ? styles.stack : styles.pair}>
            <Cell result={r.left} date={dateOf(first)} showName={r.differentNames} />
            <Cell result={r.right} date={dateOf(second)} showName={r.differentNames} />
          </View>
        </View>
      ))}
    </Screen>
  );
}

function Head({ report }: { report: LabReport }) {
  const t = useTranslations("app.timeline.compareScreen");
  const p = usePalette();
  return (
    <View style={styles.cell} accessibilityRole="header">
      <Text style={[styles.strong, { color: p.text }]}>
        {report.collected_at ? formatDate(report.collected_at) : t("noDate")}
      </Text>
      <Text style={[styles.meta, { color: p.textMuted }]}>{report.lab_name ?? t("noLab")}</Text>
    </View>
  );
}

function Cell({
  result,
  date,
  showName,
}: {
  result: LabResult | null;
  date: string;
  showName: boolean;
}) {
  const t = useTranslations("app.timeline.compareScreen");
  const tr = useTranslations("app.upload.review");
  const p = usePalette();
  if (!result) {
    return (
      <View style={styles.cell} accessible accessibilityLabel={`${date}. ${t("absent")}`}>
        <Text style={[styles.meta, { color: p.textMuted }]}>{`${date}: —`}</Text>
      </View>
    );
  }
  const token = flagToken(result.flag);
  const flagText = tr(`flags.${flagKey(result.flag)}` as "flags.unknown");
  const value = [result.raw_value, result.raw_unit].filter(Boolean).join(" ");
  const range = result.ref_text ? tr("range", { range: result.ref_text }) : tr("noRange");
  const critical = result.critical_text ? tr("critical", { range: result.critical_text }) : null;
  const name = showName ? result.raw_name : null;
  return (
    <View
      style={styles.cell}
      accessible
      accessibilityLabel={[date, name, value, flagText, range, critical].filter(Boolean).join(". ")}
    >
      <Text style={[styles.meta, { color: p.textMuted }]}>{date}</Text>
      {name && <Text style={[styles.meta, { color: p.text }]}>{name}</Text>}
      <Text style={[styles.value, { color: p.text }]}>{value}</Text>
      <View style={[styles.flag, { backgroundColor: p.flag[token].bg }]}>
        <Text style={[styles.meta, styles.strong, { color: p.flag[token].fg }]}>
          {`${flagGlyph[token]} ${flagText}`}
        </Text>
      </View>
      <Text style={[styles.meta, { color: p.textMuted }]}>{range}</Text>
      {critical && <Text style={[styles.meta, { color: p.textMuted }]}>{critical}</Text>}
    </View>
  );
}

/** Rows by test: a catalog test (else the printed name), each occurrence kept - a report may
 * hold the same test twice (blood and urine creatinine): the n-th of one report sits by the n-th
 * of the other, and the printed names are shown when they differ (never one silently dropped). */
function joinRows(
  left: LabReport,
  right: LabReport,
): {
  key: string;
  name: string;
  left: LabResult | null;
  right: LabResult | null;
  differentNames: boolean;
}[] {
  const keyOf = (r: LabResult) => r.test_code ?? `raw:${r.raw_name}`;
  const index = (rep: LabReport) => {
    const seen = new Map<string, number>();
    const m = new Map<string, LabResult>();
    for (const r of [...rep.results].sort((x, y) => x.position - y.position)) {
      const n = (seen.get(keyOf(r)) ?? 0) + 1;
      seen.set(keyOf(r), n);
      m.set(`${keyOf(r)}#${n}`, r);
    }
    return m;
  };
  const l = index(left);
  const r = index(right);
  const keys = [...l.keys(), ...[...r.keys()].filter((k) => !l.has(k))];
  return keys.map((k) => {
    const a = l.get(k) ?? null;
    const b = r.get(k) ?? null;
    const any = (a ?? b) as LabResult;
    // a test printed more than once in either report: every one of its rows shows its name
    const base = k.slice(0, k.lastIndexOf("#"));
    const twice = l.has(`${base}#2`) || r.has(`${base}#2`);
    return {
      key: k,
      name: any.test_name_mn ?? any.raw_name,
      left: a,
      right: b,
      differentNames: twice || (a !== null && b !== null && a.raw_name !== b.raw_name),
    };
  });
}

const styles = StyleSheet.create({
  heads: { flexDirection: "row", gap: space.md },
  block: { gap: space.xs },
  pair: { flexDirection: "row", gap: space.md },
  stack: { gap: space.sm },
  cell: { flex: 1, gap: space.xs },
  name: { fontSize: fontSize.body, fontWeight: "700" },
  value: { fontSize: fontSize.bodyLarge, fontWeight: "600", fontVariant: ["tabular-nums"] },
  strong: { fontSize: fontSize.body, fontWeight: "700" },
  meta: { fontSize: fontSize.body },
  flag: { alignSelf: "flex-start", borderRadius: radius.sm, paddingHorizontal: space.sm },
});
