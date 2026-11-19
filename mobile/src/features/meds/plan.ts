import type { MedicationPlan, Slot } from "./slots";
import type { Intake, IntakeStatus, Medication } from "./use-medications";

/** A medication as the slot planner reads it. The API lists the dose history newest first
 * (effective_from, then insertion order) - that order gives the planner's `seq`. */
export function planOf(med: Medication): MedicationPlan {
  const n = med.regimens.length;
  return {
    mode: med.reminder_timezone_mode === "local" ? "local" : "home",
    started_on: med.started_on,
    stopped_on: med.stopped_on,
    planned_end_on: med.planned_end_on,
    regimens: med.regimens.map((r, i) => ({
      effective_from: r.effective_from,
      seq: n - i,
      voided: r.voided_at !== null,
      schedule: r.schedule,
    })),
  };
}

export type DoseState = IntakeStatus | null;

/** A dose record waiting in the offline queue (`id` = its client_id). */
export type PendingDose = {
  id: string;
  medicationId: string;
  scheduledAt: string;
  status: IntakeStatus;
};

/** What is recorded for one planned dose, and how to undo it. */
export type Recorder = "you" | "owner" | "caregiver";
export type OtherRecord = { by: Recorder | null; takenAt: string };
export type Recorded = {
  status: IntakeStatus;
  intakeId: string | null;
  pendingIds: string[];
  /** who recorded it as taken, and when (server records only) - Q24 */
  by?: Recorder | null;
  takenAt?: string | null;
  /** other "taken" records of the same dose, kept as facts */
  also?: OtherRecord[];
};

const minute = (iso: string) => Math.floor(Date.parse(iso) / 60_000) * 60_000;

/**
 * What is recorded for each planned dose: server records plus writes still in the offline
 * queue; two records of one dose merge so that "taken" wins (H20, as on the server).
 */
export function doseStates(
  intakes: readonly Intake[],
  pending: readonly PendingDose[],
): Map<string, Recorded> {
  const out = new Map<string, Recorded>();
  const add = (
    medicationId: string,
    scheduledAt: string | null,
    status: string,
    from: { intakeId?: string; pendingId?: string },
  ) => {
    if (!scheduledAt || (status !== "taken" && status !== "late" && status !== "skipped")) return;
    const key = doseKey(medicationId, minute(scheduledAt));
    const merged: IntakeStatus = status === "skipped" ? "skipped" : "taken";
    const seen = out.get(key) ?? { status: merged, intakeId: null, pendingIds: [] };
    if (merged === "taken") seen.status = "taken";
    if (from.intakeId) seen.intakeId = from.intakeId;
    if (from.pendingId) seen.pendingIds.push(from.pendingId);
    out.set(key, seen);
  };
  for (const i of intakes) {
    add(i.medication_id, i.scheduled_at, i.status, { intakeId: i.id });
    const seen = i.scheduled_at ? out.get(doseKey(i.medication_id, minute(i.scheduled_at))) : null;
    if (seen && i.status !== "skipped") {
      seen.by = i.recorded_by ?? null;
      seen.takenAt = i.taken_at;
      seen.also = (i.also_recorded ?? []).map((x) => ({ by: x.by ?? null, takenAt: x.taken_at }));
    }
  }
  for (const p of pending) add(p.medicationId, p.scheduledAt, p.status, { pendingId: p.id });
  return out;
}

export function doseKey(medicationId: string, scheduledAt: number): string {
  return `${medicationId}@${scheduledAt}`;
}

export type TodayDose = {
  medication: Medication;
  slot: Slot;
  state: DoseState;
  recorded: Recorded | null;
  /** The zone its time is shown in: Ulaanbaatar for "home", the profile's zone for "local". */
  zone: string;
};
