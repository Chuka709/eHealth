import type { components } from "@labtrack/shared";
import { useMutation, useQuery } from "@tanstack/react-query";

import { api } from "@/lib/api";
import { queryClient } from "@/lib/query-client";
import { apiError } from "@/lib/use-error-text";

type S = components["schemas"];
export type Dashboard = S["DashboardOut"];
export type DashboardCard = S["CardOut"];
export type LatestValue = S["ValueOut"];

const key = (patientId: string) => ["dashboard", patientId] as const;

/** Home's cards and the values worth a look, as the server laid them out (rule 6); kept
 * encrypted for offline Home like the other records. */
export function useDashboard(patientId: string | undefined) {
  return useQuery({
    queryKey: key(patientId ?? ""),
    queryFn: async () => {
      const { data, error } = await api.GET("/api/v1/patients/{patient_id}/dashboard", {
        params: { path: { patient_id: patientId as string } },
      });
      if (error || !data) throw error ?? new Error("dashboard");
      return data;
    },
    enabled: patientId !== undefined,
    meta: { persist: true },
  });
}

/** The profile's own cards, in order; an empty list means none. */
export function useSaveCards(patientId: string) {
  return useMutation({
    mutationFn: async (codes: string[]) => {
      const { error, response } = await api.PUT("/api/v1/patients/{patient_id}/dashboard/cards", {
        params: { path: { patient_id: patientId } },
        body: { test_codes: codes },
      });
      if (!response.ok) throw apiError(error);
    },
    onSuccess: () => queryClient.invalidateQueries({ queryKey: key(patientId) }),
  });
}

/** Back to the organ's cards. */
export function useResetCards(patientId: string) {
  return useMutation({
    mutationFn: async () => {
      const { error, response } = await api.DELETE(
        "/api/v1/patients/{patient_id}/dashboard/cards",
        { params: { path: { patient_id: patientId } } },
      );
      if (!response.ok) throw apiError(error);
    },
    onSuccess: () => queryClient.invalidateQueries({ queryKey: key(patientId) }),
  });
}

/** A viral load's change in log10 (Q60-b): "+1.0 log", "−0.5 log". */
export function logText(delta: string): string {
  if (delta === "0" || delta === "0.0") return "0 log";
  return delta.startsWith("-") ? `−${delta.slice(1)} log` : `+${delta} log`;
}

/** "+20 %" / "−25 %" / "0 %": the server's whole percent with its sign (a number, no
 * judgement - H32). */
export function percentText(percent: string): string {
  if (percent === "0") return "0%";
  return percent.startsWith("-") ? `−${percent.slice(1)}%` : `+${percent}%`;
}
