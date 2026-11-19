import { flagGlyph, fontSize, radius, space } from "@labtrack/shared";
import { Stack, useLocalSearchParams, useRouter } from "expo-router";
import { memo, useCallback, useMemo, useState } from "react";
import { ActivityIndicator, FlatList, Pressable, StyleSheet, View } from "react-native";
import { useTranslations } from "use-intl";

import { Text } from "@/components/app-text";
import { Chart } from "@/components/chart";
import { Segmented } from "@/components/segmented";
import { LoadingView, RetryView } from "@/components/state-view";
import { Paragraph, Title } from "@/components/text";
import { useRecordProfile } from "@/features/health/record-screens";
import { flagKey, flagToken } from "@/features/review/flag";
import { type Axis, hasUndrawnDoses, trendOption } from "@/features/trends/chart-option";
import {
  PERIODS,
  type Period,
  periodStart,
  TREND_LIMIT,
  type Trend,
  type TrendPoint,
  useTrend,
} from "@/features/trends/use-trends";
import { formatDate, formatDateTime } from "@/lib/dates";
import { useErrorText } from "@/lib/use-error-text";
import { usePalette } from "@/theme/use-palette";

const CHART_HEIGHT = 260;
const AXES = ["date", "days"] as const;

/** Today's date in Ulaanbaatar (dates are shown there - CLAUDE.md), as YYYY-MM-DD. */
function todayUb(): string {
  return new Intl.DateTimeFormat("en-CA", { timeZone: "Asia/Ulaanbaatar" }).format(new Date());
}

/**
 * One test's trend (docs/06 §2, docs/08 "Хандлага"): the chart, the period and axis, then
 * every value as text in a list (never colour alone; the chart is a picture). Each value carries
 * the reference range printed on ITS result (rule 5); the recorded doses of linked medicines
 * are listed as recorded (rule 10: nothing compares a dose with a level). Tapping a value opens
 * its source result. Another period keeps the chart on screen while it loads.
 */
export default function TrendScreen() {
  const { code } = useLocalSearchParams<{ code: string }>();
  const t = useTranslations("app.trends");
  const tm = useTranslations("app.meds");
  const errorText = useErrorText();
  const p = usePalette();
  const { own } = useRecordProfile();
  const [period, setPeriod] = useState<Period>("1y");
  const [axis, setAxis] = useState<Axis>("date");
  const since = useMemo(() => periodStart(period, new Date()), [period]);
  const trend = useTrend(own?.id, code, since);
  // a dose unit is a code (mg, mcg ...): shown in the person's language (H23: one spelling each)
  const unitLabel = useCallback((u: string) => tm(`units.${u}` as "units.mg"), [tm]);
  const today = todayUb();
  const data = trend.data;
  const option = useMemo(() => {
    if (!data) return null;
    const labels = {
      value: t("seriesLabels.value"),
      refLow: t("seriesLabels.refLow"),
      refHigh: t("seriesLabels.refHigh"),
      criticalLow: t("seriesLabels.criticalLow"),
      criticalHigh: t("seriesLabels.criticalHigh"),
      dose: t("seriesLabels.dose"),
      days: t("seriesLabels.days"),
    };
    return trendOption(data, p, { axis, today, labels, unitLabel });
  }, [data, p, axis, today, t, unitLabel]);
  const newestFirst = useMemo(() => (data ? [...data.points].reverse() : []), [data]);

  if (!own) return <Paragraph muted>{t("noProfile")}</Paragraph>;
  if (!data && trend.isPending) return <LoadingView />;
  if (!data) {
    return <RetryView text={errorText(trend.error)} onRetry={() => trend.refetch()} />;
  }
  const medicine = data.doses[0];
  const approximate = data.axis?.approximate ?? false;
  const header = (
    <View style={styles.header}>
      <Stack.Screen options={{ title: data.test.name_mn }} />
      {data.points.length === 0 ? (
        <Paragraph muted>{t("noValues")}</Paragraph>
      ) : (
        option && (
          <View>
            <Chart
              option={option}
              height={CHART_HEIGHT}
              accessibilityLabel={t("chartLabel", {
                name: data.test.name_mn,
                count: data.points.length,
              })}
              testID="trend-chart"
            />
            {trend.isFetching && (
              <ActivityIndicator style={styles.busy} color={p.primary} accessibilityLabel="" />
            )}
          </View>
        )
      )}
      <Segmented
        label={t("period")}
        options={PERIODS}
        value={period}
        labelOf={(o) => t(`periods.${o}`)}
        onSelect={setPeriod}
        testID="trend-period"
      />
      {data.axis && (
        <Segmented
          label={t("axis")}
          options={AXES}
          value={axis}
          labelOf={(o) => t(`axes.${o}`)}
          onSelect={setAxis}
          testID="trend-axis"
        />
      )}
      {axis === "date" && medicine && (
        <>
          <Paragraph muted>{t("legendDose", { medicine: medicine.name })}</Paragraph>
          <Paragraph muted>{t("doseNote")}</Paragraph>
          {hasUndrawnDoses(data, today) && <Paragraph muted>{t("doseNotDrawn")}</Paragraph>}
        </>
      )}
      <Paragraph muted>{t("legend")}</Paragraph>
      {axis === "days" && approximate && <Paragraph muted>{t("daysApprox")}</Paragraph>}
      {data.truncated && <Paragraph muted>{t("truncated", { limit: TREND_LIMIT })}</Paragraph>}
      {medicine && <Doses trend={data} />}
      {newestFirst.length > 0 && <Title>{t("values")}</Title>}
    </View>
  );
  return (
    <FlatList
      testID="trend-screen"
      data={newestFirst}
      keyExtractor={(pt) => pt.result_id}
      renderItem={({ item }) => (
        <PointRow point={item} approximate={approximate} catalogName={data.test.name_mn} />
      )}
      ListHeaderComponent={header}
      style={{ backgroundColor: p.background }}
      contentContainerStyle={styles.content}
      contentInsetAdjustmentBehavior="automatic"
      initialNumToRender={20}
      windowSize={7}
    />
  );
}

const PointRow = memo(function PointRow({
  point,
  approximate,
  catalogName,
}: {
  point: TrendPoint;
  approximate: boolean;
  catalogName: string;
}) {
  const t = useTranslations("app.trends");
  const tr = useTranslations("app.upload.review");
  const router = useRouter();
  const p = usePalette();
  const token = flagToken(point.flag);
  const colour = p.flag[token];
  const flagText = tr(`flags.${flagKey(point.flag)}` as "flags.unknown");
  const value = [point.raw_value, point.raw_unit].filter(Boolean).join(" ");
  const when =
    point.collected_precision === "day"
      ? formatDate(point.collected_at)
      : formatDateTime(point.collected_at);
  const range = point.ref_text ? tr("range", { range: point.ref_text }) : tr("noRange");
  const critical = point.critical_text ? tr("critical", { range: point.critical_text }) : null;
  const days = point.around_transplant
    ? t("aroundTransplant")
    : point.days_since_transplant === null
      ? null
      : point.days_since_transplant >= 0
        ? t(approximate ? "daysAfterApprox" : "daysAfter", { days: point.days_since_transplant })
        : t(approximate ? "daysBeforeApprox" : "daysBefore", {
            days: -point.days_since_transplant,
          });
  const lab = point.lab_name ? t("lab", { lab: point.lab_name }) : null;
  // the name as printed (e.g. "eGFR (MDRD)"): which equation or method this lab used (Q70)
  const printed = sameName(point.raw_name, catalogName)
    ? null
    : t("printedName", { name: point.raw_name });
  const notDrawn = point.value === null ? t("notDrawn") : null;
  const source = point.document_id ?? point.report_id;
  return (
    <Pressable
      onPress={() => router.push(`/results/${source}`)}
      accessibilityRole="button"
      accessibilityLabel={[when, value, flagText, printed, range, critical, days, lab, notDrawn]
        .filter(Boolean)
        .join(". ")}
      accessibilityHint={t("openSource")}
      style={[styles.row, { borderTopColor: p.border }]}
      testID={`point-${point.result_id}`}
    >
      <View style={styles.line}>
        <Text style={[styles.when, { color: p.text }]}>{when}</Text>
        <Text style={[styles.value, { color: p.text }]}>{value}</Text>
      </View>
      <View style={[styles.flag, { backgroundColor: colour.bg }]}>
        <Text style={[styles.meta, styles.strong, { color: colour.fg }]}>
          {`${flagGlyph[token]} ${flagText}`}
        </Text>
      </View>
      {point.possibly_critical && token !== "critical" && (
        <View style={[styles.flag, { backgroundColor: p.flag.critical.bg }]}>
          <Text style={[styles.meta, styles.strong, { color: p.flag.critical.fg }]}>
            {`${flagGlyph.critical} ${tr("possibleCritical")}`}
          </Text>
        </View>
      )}
      {printed && <Text style={[styles.meta, { color: p.textMuted }]}>{printed}</Text>}
      <Text style={[styles.meta, { color: p.textMuted }]}>{range}</Text>
      {critical && <Text style={[styles.meta, { color: p.textMuted }]}>{critical}</Text>}
      {days && <Text style={[styles.meta, { color: p.textMuted }]}>{days}</Text>}
      {lab && <Text style={[styles.meta, { color: p.textMuted }]}>{lab}</Text>}
      {notDrawn && <Text style={[styles.meta, { color: p.textMuted }]}>{notDrawn}</Text>}
    </Pressable>
  );
});

function Doses({ trend }: { trend: Trend }) {
  const t = useTranslations("app.trends");
  const tm = useTranslations("app.meds");
  const p = usePalette();
  return (
    <View style={styles.doses} testID="trend-doses">
      {trend.doses.map((d) => (
        <View key={d.medication_id} style={styles.doses}>
          <Title>{t("doses", { medicine: d.name })}</Title>
          {d.series.flatMap((s) =>
            [...s.steps].reverse().map((step) => {
              const unit = s.unit_text ?? (s.unit ? tm(`units.${s.unit}` as "units.mg") : "");
              const from = formatDate(step.starts_on);
              const text =
                step.amount === null
                  ? t("doseNone", { from })
                  : step.schedule_type === "weekly"
                    ? t("doseStepWeekly", { from, amount: step.amount, unit })
                    : t("doseStep", { from, amount: step.amount, unit });
              return (
                <Text
                  key={`${s.unit}-${s.unit_text}-${step.starts_on}`}
                  style={[styles.meta, styles.tabular, { color: p.text }]}
                >
                  {step.planned ? `${t("dosePlanned")}: ${text}` : text}
                </Text>
              );
            }),
          )}
        </View>
      ))}
    </View>
  );
}

const styles = StyleSheet.create({
  content: { padding: space.lg },
  header: { gap: space.lg, paddingBottom: space.sm },
  busy: { position: "absolute", top: space.sm, right: space.sm },
  doses: { gap: space.sm },
  row: { gap: space.xs, paddingVertical: space.sm, borderTopWidth: StyleSheet.hairlineWidth },
  line: { flexDirection: "row", justifyContent: "space-between", gap: space.sm, flexWrap: "wrap" },
  when: { fontSize: fontSize.body },
  value: { fontSize: fontSize.bodyLarge, fontWeight: "600", fontVariant: ["tabular-nums"] },
  flag: { alignSelf: "flex-start", borderRadius: radius.sm, paddingHorizontal: space.sm },
  meta: { fontSize: fontSize.body },
  tabular: { fontVariant: ["tabular-nums"] },
  strong: { fontWeight: "600" },
});

/** The printed name says nothing more than the catalog name, with or without its "(…)" part. */
function sameName(printed: string, catalog: string): boolean {
  const norm = (x: string) => x.trim().toLocaleLowerCase();
  const name = norm(printed);
  return name === norm(catalog) || name === norm(catalog.replace(/\s*\([^)]*\)\s*$/, ""));
}
