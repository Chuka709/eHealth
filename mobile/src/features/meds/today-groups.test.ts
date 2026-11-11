import type { TodayDose } from "./plan";
import { byTime } from "./today-list";

const dose = (id: string, at: number, zone: string) =>
  ({ medication: { id }, slot: { scheduledAt: at, at: "08:00" }, zone }) as unknown as TodayDose;

test("doses of one instant share a group; the same clock text at another instant does not", () => {
  const ub = Date.parse("2026-11-12T00:00:00Z"); // 08:00 Ulaanbaatar
  const seoul = Date.parse("2026-11-11T23:00:00Z"); // 08:00 Seoul, an hour earlier
  const groups = byTime([
    dose("a", seoul, "Asia/Seoul"),
    dose("b", ub, "Asia/Ulaanbaatar"),
    dose("c", ub, "Asia/Ulaanbaatar"),
  ]);
  expect(groups.map((g) => [g.time, g.items.map((d) => d.medication.id)])).toEqual([
    ["08:00", ["a"]],
    ["08:00", ["b", "c"]],
  ]);
  // every group has its own key: no dose is dropped by React (medical review 2.12)
  expect(new Set(groups.map((g) => g.key)).size).toBe(groups.length);
});
