import { useMemo, useState } from "react";
import { View } from "react-native";
import { useTranslations } from "use-intl";

import { Chart } from "@/components/chart";
import { Segmented } from "@/components/segmented";
import { Paragraph } from "@/components/text";
import { usePalette } from "@/theme/use-palette";

import type { Vital } from "./use-health";

const CHART_HEIGHT = 200;
const NOT_A_TREND = new Set(["urine_output", "fluid_intake"]);
// blood pressure is one chart of its two numbers
const CHARTS: Record<string, string[]> = {
  bp: ["bp_systolic", "bp_diastolic"],
};

/**
 * The person's own readings over time (docs/08 "Амин үзүүлэлт"; Phase 6.9): one kind at a time,
 * as entered, in its unit. No range is drawn - the app sets none for vitals (a doctor's target
 * comes with Phase 7) - and nothing is judged. Shown when a kind has at least two readings;
 * every reading is also listed under it (the chart is a picture).
 */
export function VitalsChart({ vitals }: { vitals: readonly Vital[] }) {
  const t = useTranslations("app.health.vital");
  const p = usePalette();
  const byChart = useMemo(() => {
    const out = new Map<string, Vital[]>();
    for (const v of vitals) {
      // one-off amounts ("this time"), not a daily total: never joined into a line (H26)
      if (NOT_A_TREND.has(v.kind)) continue;
      const chart = v.kind === "bp_systolic" || v.kind === "bp_diastolic" ? "bp" : v.kind;
      out.set(chart, [...(out.get(chart) ?? []), v]);
    }
    return [...out.entries()].filter(([chart, rows]) =>
      (CHARTS[chart] ?? [chart]).every((k) => rows.filter((r) => r.kind === k).length >= 2),
    );
  }, [vitals]);
  const kinds = byChart.map(([k]) => k);
  const [chosen, setChosen] = useState<string | null>(null);
  const kind = chosen && kinds.includes(chosen) ? chosen : (kinds[0] ?? null);
  const rows = byChart.find(([k]) => k === kind)?.[1] ?? [];
  const option = useMemo(() => {
    const parts = kind ? (CHARTS[kind] ?? [kind]) : [];
    const colours = [p.primary, p.done.fg];
    return {
      animation: false,
      grid: { left: 44, right: 16, top: 24, bottom: 32 },
      xAxis: {
        type: "time",
        axisLabel: { color: p.textMuted, hideOverlap: true, formatter: "{yyyy}.{MM}.{dd}" },
      },
      yAxis: {
        type: "value",
        scale: true,
        name: rows[0]?.unit ?? "",
        axisLabel: { color: p.textMuted },
        splitLine: { lineStyle: { color: p.border } },
      },
      tooltip: { show: false },
      series: parts.map((part, i) => ({
        name: part,
        type: "line",
        symbol: i === 0 ? "circle" : "triangle",
        symbolSize: 7,
        lineStyle: {
          color: colours[i % colours.length],
          width: 2,
          type: i === 0 ? "solid" : "dashed",
        },
        itemStyle: { color: colours[i % colours.length] },
        data: rows
          .filter((r) => r.kind === part)
          .sort((a, b) => a.measured_at.localeCompare(b.measured_at))
          .map((r) => [r.measured_at, Number(r.value)]),
      })),
    };
  }, [kind, rows, p]);
  if (kind === null) return null;
  return (
    <View testID="vitals-chart">
      {kinds.length > 1 && (
        <Segmented
          label={t("chartKind")}
          options={kinds}
          value={kind}
          labelOf={(k) => t(`kinds.${k}` as "kinds.pulse")}
          onSelect={setChosen}
        />
      )}
      <Chart
        option={option}
        height={CHART_HEIGHT}
        accessibilityLabel={t("chartLabel", {
          kind: t(`kinds.${kind}` as "kinds.pulse"),
          count: rows.length,
        })}
      />
      <Paragraph muted>{t("chartPeriod")}</Paragraph>
      {kind === "bp" && <Paragraph muted>{t("chartBpLegend")}</Paragraph>}
    </View>
  );
}
