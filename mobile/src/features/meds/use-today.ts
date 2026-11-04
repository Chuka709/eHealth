import { useQuery } from "@tanstack/react-query";
import { useMemo } from "react";

import { pendingWrites } from "@/features/offline/queue";

import { doseKey, doseStates, type PendingDose, planOf, type TodayDose } from "./plan";
import { doseSlots, HOME_TIMEZONE } from "./slots";
import { useIntakes, useMedications, useZones } from "./use-medications";

export const pendingDosesKey = (patientId: string) => ["queue", "doses", patientId] as const;

/** Dose records still waiting in the offline queue for this profile. */
export function usePendingDoses(patientId: string | undefined) {
  return useQuery({
    queryKey: pendingDosesKey(patientId ?? ""),
    enabled: Boolean(patientId),
    networkMode: "always",
    queryFn: async (): Promise<PendingDose[]> => {
      const path = `/api/v1/patients/${patientId}/intakes`;
      return (await pendingWrites())
        .filter((w) => w.path === path)
        .map((w) => ({
          id: w.id,
          medicationId: String(w.body.medication_id),
          scheduledAt: String(w.body.scheduled_at),
          status: w.body.status === "skipped" ? ("skipped" as const) : ("taken" as const),
        }));
    },
  });
}

/** The phone's calendar day [start, end) as epoch ms (where the user is now). */
export function localDay(now: Date): { start: number; end: number } {
  const start = new Date(now.getFullYear(), now.getMonth(), now.getDate()).getTime();
  const end = new Date(now.getFullYear(), now.getMonth(), now.getDate() + 1).getTime();
  return { start, end };
}

/**
 * Today's planned doses (the phone's day) with what is recorded for each - computed on the
 * phone from the cached dose history and zone, so it works offline.
 */
export function useTodayDoses(patientId: string | undefined, now: Date) {
  const { start, end } = localDay(now);
  const meds = useMedications(patientId);
  const zones = useZones(patientId);
  const intakes = useIntakes(patientId, new Date(start).toISOString(), new Date(end).toISOString());
  const pending = usePendingDoses(patientId);

  const doses = useMemo<TodayDose[]>(() => {
    if (!meds.data) return [];
    const states = doseStates(intakes.data ?? [], pending.data ?? []);
    const switches = zones.data?.switches ?? [];
    const local = zones.data?.current ?? HOME_TIMEZONE;
    return meds.data
      .flatMap((medication) =>
        doseSlots(planOf(medication), switches, start, end).map((slot) => {
          const recorded = states.get(doseKey(medication.id, slot.scheduledAt)) ?? null;
          return {
            medication,
            slot,
            recorded,
            state: recorded?.status ?? null,
            zone: medication.reminder_timezone_mode === "local" ? local : HOME_TIMEZONE,
          };
        }),
      )
      .sort((a, b) => a.slot.scheduledAt - b.slot.scheduledAt);
  }, [meds.data, zones.data, intakes.data, pending.data, start, end]);

  return { doses, meds, zones, intakes };
}
