import type { Transplant } from "./use-transplants";

type Dated = Pick<Transplant, "elapsed" | "date_precision" | "transplant_date">;

type T = (key: string, values?: Record<string, string | number>) => string;

/**
 * "Time since" as the server computed it (core/timeline: never overstated). A year-only date
 * shows the year itself, a month-only date is marked "≈" - never a precise-looking count.
 */
export function elapsedText(t: T, transplant: Dated): string | null {
  const e = transplant.elapsed;
  if (!e) return null;
  if (transplant.date_precision === "year") {
    return t("summary.sinceYearOnly", { year: transplant.transplant_date.slice(0, 4) });
  }
  if (e.years === 0) return t("summary.sinceMonths", { months: e.months });
  const values = { years: e.years, months: e.months % 12 };
  return e.approximate ? t("summary.since", values) : t("summary.sinceExact", values);
}

/** The date as the user gave it: YYYY.MM.DD, YYYY.MM or YYYY. */
export function transplantDateText(transplant: Dated): string {
  const [y, m, d] = transplant.transplant_date.split("-");
  if (transplant.date_precision === "year") return `${y}`;
  if (transplant.date_precision === "month") return `${y}.${m}`;
  return `${y}.${m}.${d}`;
}
