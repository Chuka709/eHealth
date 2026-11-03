import type { components } from "@labtrack/shared";
import { useMutation, useQuery } from "@tanstack/react-query";

import { api } from "@/lib/api";
import { queryClient } from "@/lib/query-client";
import { apiError } from "@/lib/use-error-text";

export type DeviceSession = components["schemas"]["SessionOut"];

const sessionsKey = ["auth", "sessions"] as const;

/** Signed-in devices, this one first. */
export function useSessions() {
  return useQuery({
    queryKey: sessionsKey,
    queryFn: async () => {
      const { data, error } = await api.GET("/api/v1/auth/sessions");
      if (!data) throw apiError(error);
      return [...data].sort((a, b) => Number(b.current) - Number(a.current));
    },
  });
}

/** Ends another device's session (this device signs out through the normal sign-out). */
export function useRevokeSession() {
  return useMutation({
    mutationFn: async (sessionId: string) => {
      const { error, response } = await api.DELETE("/api/v1/auth/sessions/{session_id}", {
        params: { path: { session_id: sessionId } },
      });
      if (!response.ok) throw apiError(error);
    },
    onSettled: () => queryClient.invalidateQueries({ queryKey: sessionsKey }),
  });
}
