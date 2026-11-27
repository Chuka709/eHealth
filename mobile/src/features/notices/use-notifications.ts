import type { components } from "@labtrack/shared";
import { useMutation, useQuery } from "@tanstack/react-query";

import { api } from "@/lib/api";
import { queryClient } from "@/lib/query-client";
import { apiError } from "@/lib/use-error-text";

export type Notice = components["schemas"]["NotificationOut"];
export type DoseAlert = components["schemas"]["DoseAlertOut"];

// under ["me", "notifications"]: marking one read refreshes the admin notices on Home too
export const allNoticesKey = ["me", "notifications", "all"] as const;

/** The user's notifications, newest first (only those about profiles they can still open). */
export function useNotices() {
  return useQuery({
    queryKey: allNoticesKey,
    // a push may have just announced a new one (2.8f-1 M1)
    staleTime: 0,
    refetchOnMount: "always",
    queryFn: async () => {
      const { data, error } = await api.GET("/api/v1/me/notifications");
      if (!data) throw apiError(error);
      return data;
    },
  });
}

/** A push arrived or was tapped: the list (and the 🔔 count) is read again. */
export function refreshNotices(): Promise<void> {
  return queryClient.invalidateQueries({ queryKey: ["me", "notifications"] });
}

export function unreadCount(notices: readonly Notice[] | undefined): number {
  return (notices ?? []).filter((n) => n.read_at === null).length;
}

/** What a dose alert was about, and what is recorded for that dose now (decision 3). */
export function useDoseAlert(patientId: string | null, alertId: number | null) {
  return useQuery({
    queryKey: ["dose-alert", patientId, alertId],
    enabled: patientId !== null && alertId !== null,
    queryFn: async () => {
      const { data, error } = await api.GET(
        "/api/v1/patients/{patient_id}/dose-alerts/{alert_id}",
        {
          params: { path: { patient_id: patientId ?? "", alert_id: alertId ?? 0 } },
        },
      );
      if (!data) throw apiError(error);
      return data;
    },
  });
}

export function useMarkRead() {
  return useMutation({
    mutationFn: async (id: number) => {
      const { error, response } = await api.POST(
        "/api/v1/me/notifications/{notification_id}/read",
        { params: { path: { notification_id: id } } },
      );
      if (!response.ok) throw apiError(error);
    },
    onSettled: () => queryClient.invalidateQueries({ queryKey: ["me", "notifications"] }),
  });
}
