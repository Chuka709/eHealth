import { useEffect, useMemo, useState } from "react";

import type { Appointment } from "@/features/health/use-health";
import type { TodayDose } from "@/features/meds/plan";
import { localDay } from "@/features/meds/use-today";
import type { Transplant } from "@/features/records/use-transplants";

/** One row of today's doses, the same key the Эм tab's list uses. */
export function doseRowKey(dose: TodayDose): string {
  return `${dose.medication.id}@${dose.slot.scheduledAt}@${dose.slot.at}`;
}

/**
 * The doses Home offers to record: those due and not recorded yet, and the next ones coming
 * (every dose at that same time). A row once shown stays (`kept`), so the "Буцаах" that replaces
 * "Уусан" is still there after a tap. Nothing here calls a dose late or missed (Q23).
 */
export function homeDoses(
  doses: readonly TodayDose[],
  now: number,
  kept: ReadonlySet<string>,
): TodayDose[] {
  const next = doses.find((d) => d.state === null && d.slot.scheduledAt > now)?.slot.scheduledAt;
  return doses.filter(
    (d) =>
      kept.has(doseRowKey(d)) ||
      (d.state === null && (d.slot.scheduledAt <= now || d.slot.scheduledAt === next)),
  );
}

/** How many of today's doses have a record (taken or skipped) - a count, never a judgement. */
export function doseCounts(doses: readonly TodayDose[]): { recorded: number; total: number } {
  return { recorded: doses.filter((d) => d.state !== null).length, total: doses.length };
}

export function useHomeDoses(doses: readonly TodayDose[], now: number): TodayDose[] {
  const [kept, setKept] = useState<ReadonlySet<string>>(() => new Set());
  const shown = useMemo(() => homeDoses(doses, now, kept), [doses, now, kept]);
  useEffect(() => {
    const added = shown.map(doseRowKey).filter((k) => !kept.has(k));
    if (added.length > 0) setKept(new Set([...kept, ...added]));
  }, [shown, kept]);
  return shown;
}

/** The latest transplant: the highest number, then the latest date (a re-transplant first). */
export function latestTransplant(list: readonly Transplant[]): Transplant | undefined {
  return [...list].sort(
    (a, b) =>
      b.transplant_number - a.transplant_number ||
      b.transplant_date.localeCompare(a.transplant_date),
  )[0];
}

/**
 * The next planned appointment: the soonest from the start of today (the phone's day), so one
 * that began a little while ago still shows today; cancelled and done ones are never next.
 */
export function nextAppointment(list: readonly Appointment[], now: Date): Appointment | undefined {
  const from = localDay(now).start;
  return list
    .filter((a) => a.status === "planned" && Date.parse(a.scheduled_at) >= from)
    .sort((a, b) => Date.parse(a.scheduled_at) - Date.parse(b.scheduled_at))[0];
}
