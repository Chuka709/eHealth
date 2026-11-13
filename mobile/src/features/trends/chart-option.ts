import type { EChartsCoreOption } from "echarts/core";

import type { usePalette } from "@/theme/use-palette";

import type { Trend, TrendPoint } from "./use-trends";

type Palette = ReturnType<typeof usePalette>;
export type Axis = "date" | "days";

/**
 * The ECharts option of one test's trend (docs/06 §2). It only lays out what the server sent
 * (rule 6): values and ranges are drawn as they came (strings turned into numbers for the
 * plot), nothing is compared, smoothed or judged.
 *
 * - the value line; a point's symbol: hollow when the value was "< x"/"> x" (never drawn as an
 *   exact value) or had no range, else a diamond when critical, a triangle above/below range, a
 *   circle within it
 * - the reference limits of EACH point's document as thin step lines - a change of lab shows
 *   as a step (rule 5); critical limits dashed
 * - the recorded daily doses of the first linked medicine (its latest unit) as a dashed step
 *   on a second axis - date axis only; up to today only: a step entered ahead (`planned`) and
 *   a weekly schedule (an amount per dosing day, not per day) are listed, not drawn (H33)
 * - transplants and clinical events as dotted vertical lines (date axis only)
 * No tooltip and no zoom: every value is listed under the chart with its unit and comparator.
 */
export function trendOption(
  trend: Trend,
  p: Palette,
  {
    axis,
    today,
    labels,
    unitLabel,
  }: { axis: Axis; today: string; labels: Labels; unitLabel: (unit: string) => string },
): EChartsCoreOption {
  const points = trend.points.filter((pt) => pt.value !== null && xOf(pt, axis) !== null);
  const at = (pt: TrendPoint) => xOf(pt, axis) as string | number;
  const num = (v: string | null) => (v === null ? null : Number(v));
  const step = (pick: (pt: TrendPoint) => string | null) =>
    points.map((pt) => [at(pt), num(pick(pt))]);
  const hasCritical = points.some((pt) => pt.critical_low !== null || pt.critical_high !== null);
  const dose = axis === "date" ? firstDoseSeries(trend, today, unitLabel) : null;

  const series: Record<string, unknown>[] = [
    limitLine(
      labels.refLow,
      step((pt) => pt.ref_low),
      p.textMuted,
      "solid",
    ),
    limitLine(
      labels.refHigh,
      step((pt) => pt.ref_high),
      p.textMuted,
      "solid",
    ),
  ];
  if (hasCritical) {
    series.push(
      limitLine(
        labels.criticalLow,
        step((pt) => pt.critical_low),
        p.flag.critical.bg,
        "dashed",
      ),
      limitLine(
        labels.criticalHigh,
        step((pt) => pt.critical_high),
        p.flag.critical.bg,
        "dashed",
      ),
    );
  }
  series.push({
    name: labels.value,
    type: "line",
    z: 5,
    data: points.map((pt) => ({
      value: [at(pt), num(pt.value)],
      symbol: symbolOf(pt),
      symbolSize: pt.flag.startsWith("critical") ? 12 : 9,
      itemStyle: { color: colourOf(pt, p) },
    })),
    lineStyle: { color: p.primary, width: 2 },
    markLine:
      axis === "date"
        ? {
            symbol: "none",
            silent: true,
            label: { show: false },
            lineStyle: { color: p.textMuted, type: "dotted", width: 1 },
            data: eventDays(trend).map((d) => ({ xAxis: d })),
          }
        : undefined,
  });
  if (dose) {
    series.push({
      name: labels.dose,
      type: "line",
      yAxisIndex: 1,
      step: "end",
      symbol: "none",
      connectNulls: false,
      lineStyle: { color: p.done.fg, width: 2, type: "dashed" },
      data: dose.data,
    });
  }

  return {
    animation: false,
    grid: { left: 44, right: dose ? 44 : 16, top: 24, bottom: 32 },
    xAxis:
      axis === "date"
        ? {
            type: "time",
            axisLabel: { color: p.textMuted, hideOverlap: true, formatter: "{yyyy}.{MM}" },
          }
        : { type: "value", axisLabel: { color: p.textMuted }, name: labels.days },
    yAxis: [
      {
        type: "value",
        scale: true,
        // a little room under the lowest line, so a lower limit never sits on the axis
        min: (v: { min: number; max: number }) => {
          const below = Math.floor(v.min - (v.max - v.min) * 0.1);
          return v.min >= 0 ? Math.max(0, below) : below; // never below 0 for positive values
        },
        name: trend.test.unit ?? "",
        axisLabel: { color: p.textMuted },
        splitLine: { lineStyle: { color: p.border } },
      },
      ...(dose
        ? [
            {
              type: "value",
              min: 0,
              // headroom: the top step does not sit on the left axis's top grid line
              max: (v: { max: number }) => Math.ceil(v.max * 1.25),
              name: dose.unit,
              axisLabel: { color: p.done.fg },
              splitLine: { show: false },
            },
          ]
        : []),
    ],
    tooltip: { show: false },
    series,
  };
}

export type Labels = {
  value: string;
  refLow: string;
  refHigh: string;
  criticalLow: string;
  criticalHigh: string;
  dose: string;
  days: string;
};

function xOf(pt: TrendPoint, axis: Axis): string | number | null {
  return axis === "date" ? pt.collected_at : pt.days_since_transplant;
}

function limitLine(name: string, data: unknown[], color: string, type: "solid" | "dashed") {
  return {
    name,
    type: "line",
    step: "middle",
    symbol: "none",
    silent: true,
    connectNulls: false,
    lineStyle: { color, width: 1, type, opacity: 0.9 },
    data,
  };
}

/** A "< x" is a bound, not a value: hollow first, whatever its flag (then the flag's shape). */
export function symbolOf(pt: TrendPoint): string {
  if (pt.comparator !== null) return "emptyTriangle";
  if (pt.flag === "no_reference" || pt.flag === "unknown") return "emptyCircle";
  if (pt.flag === "critical_low" || pt.flag === "critical_high") return "diamond";
  if (pt.flag === "low" || pt.flag === "high" || pt.flag === "abnormal") return "triangle";
  return "circle";
}

function colourOf(pt: TrendPoint, p: Palette): string {
  if (pt.flag === "critical_low" || pt.flag === "critical_high") return p.flag.critical.bg;
  if (pt.flag === "low") return p.flag.low.fg;
  if (pt.flag === "high" || pt.flag === "abnormal") return p.flag.high.fg;
  if (pt.flag === "normal") return p.flag.normal.fg;
  return p.textMuted;
}

function eventDays(trend: Trend): string[] {
  return [
    ...trend.transplants.map((t) => t.transplant_date),
    ...trend.events.map((e) => e.started_on),
  ];
}

/** The daily steps of the first linked medicine's latest-unit series, up to today: a step runs
 * until the next one or its end; a gap (null) where none was recorded. A step entered ahead,
 * a weekly one or one without an amount is not drawn. Only one dose axis. */
function firstDoseSeries(
  trend: Trend,
  today: string,
  unitLabel: (unit: string) => string,
): { unit: string; data: [string, number | null][] } | null {
  const medicine = trend.doses[0];
  const latest = medicine?.series.at(-1);
  if (!medicine || !latest) return null;
  const data: [string, number | null][] = [];
  for (const s of latest.steps) {
    if (s.planned || s.starts_on > today) continue;
    const end = s.ends_before !== null && s.ends_before < today ? s.ends_before : today;
    if (s.amount === null || s.schedule_type !== "daily") {
      data.push([s.starts_on, null]);
      continue;
    }
    const amount = Number(s.amount);
    data.push([s.starts_on, amount], [end, amount]);
    if (end !== today) data.push([end, null]);
  }
  if (!data.some(([, v]) => v !== null)) return null;
  return { unit: latest.unit_text ?? (latest.unit ? unitLabel(latest.unit) : ""), data };
}

/** Whether a medicine has steps the chart leaves out (weekly, planned, another unit). */
export function hasUndrawnDoses(trend: Trend, today: string): boolean {
  const medicine = trend.doses[0];
  if (!medicine) return false;
  if (medicine.series.length > 1) return true;
  return medicine.series.some((s) =>
    s.steps.some((st) => st.planned || st.starts_on > today || st.schedule_type !== "daily"),
  );
}
