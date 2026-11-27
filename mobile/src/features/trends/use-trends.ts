import type { components } from "@labtrack/shared";
import { keepPreviousData, useQuery } from "@tanstack/react-query";

import { api } from "@/lib/api";

type S = components["schemas"];
export type Tested = S["TestedOut"];
export type Trend = S["TrendOut"];
export type TrendPoint = S["TrendPointOut"];
export type DoseSeries = S["DoseSeriesOut"];

export const TREND_LIMIT = 2000; // the server sends at most this many points

export const PERIODS = ["3m", "6m", "1y", "5y", "all"] as const;
export type Period = (typeof PERIODS)[number];

const MONTHS: Record<Exclude<Period, "all">, number> = { "3m": 3, "6m": 6, "1y": 12, "5y": 60 };

/** The start of a period, from now (which values the chart asks for - not a computation on
 * them). */
export function periodStart(period: Period, now: Date): string | undefined {
  if (period === "all") return undefined;
  const start = new Date(now);
  start.setMonth(start.getMonth() - MONTHS[period]);
  return start.toISOString();
}

/** The tests the profile has confirmed values of, most recent first. */
export function useTested(patientId: string | undefined) {
  return useQuery({
    queryKey: ["trends", patientId],
    queryFn: async () => {
      const { data, error } = await api.GET("/api/v1/patients/{patient_id}/trends", {
        params: { path: { patient_id: patientId as string } },
      });
      if (error || !data) throw error ?? new Error("trends");
      return data;
    },
    enabled: patientId !== undefined,
  });
}

/** One test's trend as the server laid it out (rule 6): points with their own ranges, the
 * recorded doses of linked medicines, events, days since transplant. */
export function useTrend(patientId: string | undefined, code: string, since: string | undefined) {
  return useQuery({
    queryKey: ["trends", patientId, code, since ?? "all"],
    queryFn: async () => {
      const { data, error } = await api.GET("/api/v1/patients/{patient_id}/trends/{test_code}", {
        params: { path: { patient_id: patientId as string, test_code: code }, query: { since } },
      });
      if (error || !data) throw error ?? new Error("trend");
      return data;
    },
    // another period keeps the chart on screen until the new values arrive
    placeholderData: keepPreviousData,
    enabled: patientId !== undefined,
  });
}
