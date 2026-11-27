import type { components } from "@labtrack/shared";
import { keepPreviousData, useInfiniteQuery, useQuery } from "@tanstack/react-query";

import { api } from "@/lib/api";

type S = components["schemas"];
export type TimelineItem = S["TimelineItem"];
export type Kind = TimelineItem["kind"];

/** The filter groups shown to the person; "medication" is the three medicine kinds. */
export const GROUPS = ["transplant", "medication", "event", "report"] as const;
export type Group = (typeof GROUPS)[number];
const KINDS_OF: Record<Group, Kind[]> = {
  transplant: ["transplant"],
  medication: ["medication_started", "medication_stopped", "regimen_changed"],
  event: ["event"],
  report: ["report"],
};

export function kindsOf(groups: readonly Group[]): Kind[] {
  return groups.flatMap((g) => KINDS_OF[g]);
}

/** One stream, newest first, a page at a time (the server's keyset cursor). */
export function useTimeline(
  patientId: string | undefined,
  groups: readonly Group[],
  lab: string | null,
) {
  const kinds = kindsOf(groups);
  return useInfiniteQuery({
    queryKey: ["timeline", patientId, kinds.join(","), lab ?? ""],
    initialPageParam: undefined as string | undefined,
    queryFn: async ({ pageParam }) => {
      const { data, error } = await api.GET("/api/v1/patients/{patient_id}/timeline", {
        params: {
          path: { patient_id: patientId as string },
          query: { kinds, lab: lab ?? undefined, cursor: pageParam, limit: 50 },
        },
      });
      if (error || !data) throw error ?? new Error("timeline");
      return data;
    },
    getNextPageParam: (last) => last.next ?? undefined,
    // another filter keeps the list (and the filters) on screen until it arrives
    placeholderData: keepPreviousData,
    enabled: patientId !== undefined && kinds.length > 0,
  });
}

/** The labs of the profile's confirmed reports, for the filter. */
export function useLabs(patientId: string | undefined) {
  return useQuery({
    queryKey: ["timeline-labs", patientId],
    queryFn: async () => {
      const { data, error } = await api.GET("/api/v1/patients/{patient_id}/timeline/labs", {
        params: { path: { patient_id: patientId as string } },
      });
      if (error || !data) throw error ?? new Error("labs");
      return data;
    },
    enabled: patientId !== undefined,
  });
}

/** The heading an item sits under: its month ("2026-10"), or only its year ("2021") for a
 * transplant known only to the year - never a month it may not be in (H24, H34). */
export function sectionOf(item: TimelineItem): string {
  if (item.kind === "transplant" && item.precision === "year") return item.day.slice(0, 4);
  return item.day.slice(0, 7);
}
