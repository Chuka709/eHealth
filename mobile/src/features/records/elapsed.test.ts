import mn from "@labtrack/shared/messages/mn.json";

import { elapsedText } from "./elapsed";

const summary = mn.app.transplant.summary as Record<string, string>;
const t = (key: string, values: Record<string, string | number> = {}) =>
  (summary[key.replace("summary.", "")] ?? key).replace(/\{(\w+)\}/g, (_, k) => String(values[k]));

const at = (precision: string, days: number, months: number, approximate: boolean) => ({
  transplant_date: "2026-10-01",
  date_precision: precision,
  elapsed: { days, months, years: Math.floor(months / 12), approximate },
});

test("H24: an exact count in the first months only from an exact date", () => {
  expect(elapsedText(t, at("day", 12, 0, false))).toBe("12 хоног өнгөрсөн");
  // counted from the month's end: never "under a month", which could be untrue
  expect(elapsedText(t, at("month", 0, 0, true))).toBe("2026 оны 10-р сард");
  expect(elapsedText(t, at("day", 70, 2, false))).toBe("2 сар өнгөрсөн");
  expect(elapsedText(t, at("month", 70, 2, true))).toBe("Ойролцоогоор 2 сар өнгөрсөн");
  expect(elapsedText(t, at("month", 900, 29, true))).toBe("Ойролцоогоор 2 жил 5 сар өнгөрсөн");
});
