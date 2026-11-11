import type { TodayDose } from "@/features/meds/plan";

import { doseCounts, doseRowKey, homeDoses } from "./home-data";

const dose = (at: string, scheduledAt: number, state: TodayDose["state"] = null): TodayDose =>
  ({
    medication: { id: "m1" },
    slot: { at, scheduledAt },
    state,
    recorded: null,
    zone: "Asia/Ulaanbaatar",
  }) as unknown as TodayDose;

const day = [
  dose("08:00", 800),
  dose("12:00", 1200, "taken"),
  dose("14:00", 1400),
  dose("20:00", 2000),
  dose("20:00b", 2000),
  dose("22:00", 2200),
];
const ats = (list: TodayDose[]) => list.map((d) => d.slot.at);

test("due unrecorded doses and every dose at the next time; nothing recorded or later", () => {
  expect(ats(homeDoses(day, 1500, new Set()))).toEqual(["08:00", "14:00", "20:00", "20:00b"]);
});

test("before the first dose only the next ones show", () => {
  expect(ats(homeDoses(day, 100, new Set()))).toEqual(["08:00"]);
});

test("a row shown once stays after it is recorded (its undo stays reachable)", () => {
  const recorded = day.map((d) => (d.slot.at === "08:00" ? { ...d, state: "taken" as const } : d));
  const kept = new Set([doseRowKey(day[0])]);
  expect(ats(homeDoses(recorded, 100, kept))).toEqual(["08:00", "14:00"]);
});

test("counts are plain numbers of records, skipped included", () => {
  expect(doseCounts([...day, dose("23:00", 2300, "skipped")])).toEqual({ recorded: 2, total: 7 });
});
