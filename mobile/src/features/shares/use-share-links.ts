import type { components } from "@labtrack/shared";
import { useMutation, useQuery } from "@tanstack/react-query";

import { api } from "@/lib/api";
import { queryClient } from "@/lib/query-client";
import { apiError } from "@/lib/use-error-text";

/**
 * Share links (Phase 7.2; API 0041): the owner makes a time-limited, read-only link to chosen
 * sections, opened on the web with a 6-digit PIN. The token and the PIN come back once, live
 * only in the screen's state (never in the query cache or on disk) and cannot be read again.
 */

export type ShareLink = components["schemas"]["ShareLinkOut"];
export type ShareLinkIn = components["schemas"]["ShareLinkIn"];
export type ShareLinkCreated = components["schemas"]["ShareLinkCreatedOut"];
export type ShareScope = ShareLinkIn["scopes"][number];

export const SCOPES: readonly ShareScope[] = [
  "summary",
  "labs",
  "meds",
  "transplant",
  "events",
  "vitals",
];

const linksKey = (patientId: string | undefined) => ["share-links", patientId] as const;

export function useShareLinks(patientId: string | undefined, { enabled = true } = {}) {
  return useQuery({
    queryKey: linksKey(patientId),
    enabled: enabled && patientId !== undefined,
    staleTime: 0,
    queryFn: async () => {
      const { data, error } = await api.GET("/api/v1/patients/{patient_id}/share-links", {
        params: { path: { patient_id: patientId ?? "" } },
      });
      if (!data) throw apiError(error);
      return data;
    },
  });
}

/** When a link was opened (fetched only when the owner asks for it). */
export function useShareLinkViews(patientId: string, linkId: string | null) {
  return useQuery({
    queryKey: ["share-link-views", patientId, linkId],
    enabled: linkId !== null,
    staleTime: 0,
    queryFn: async () => {
      const { data, error } = await api.GET(
        "/api/v1/patients/{patient_id}/share-links/{link_id}/views",
        { params: { path: { patient_id: patientId, link_id: linkId ?? "" } } },
      );
      if (!data) throw apiError(error);
      return data;
    },
  });
}

export function useCreateShareLink(patientId: string) {
  return useMutation({
    // gcTime 0: the answer (token, PIN) is not kept by the mutation cache after the screen
    gcTime: 0,
    mutationFn: async (body: ShareLinkIn): Promise<ShareLinkCreated> => {
      const { data, error } = await api.POST("/api/v1/patients/{patient_id}/share-links", {
        params: { path: { patient_id: patientId } },
        body,
      });
      if (!data) throw apiError(error);
      return data;
    },
    onSettled: () => void queryClient.invalidateQueries({ queryKey: linksKey(patientId) }),
  });
}

export function useRevokeShareLink(patientId: string) {
  return useMutation({
    mutationFn: async (linkId: string) => {
      const { error, response } = await api.DELETE(
        "/api/v1/patients/{patient_id}/share-links/{link_id}",
        { params: { path: { patient_id: patientId, link_id: linkId } } },
      );
      if (!response.ok) throw apiError(error);
    },
    onSettled: () => void queryClient.invalidateQueries({ queryKey: linksKey(patientId) }),
  });
}

export type LinkState = "active" | "expired" | "used_up" | "revoked" | "pin_locked";

/** What the owner sees on a link's card (display only; the server decides who may open it). */
export function linkState(link: ShareLink, now: Date = new Date()): LinkState {
  if (link.revoked_at) return link.revoked_reason === "pin_locked" ? "pin_locked" : "revoked";
  if (new Date(link.expires_at) <= now) return "expired";
  if (link.max_views !== null && link.view_count >= link.max_views) return "used_up";
  return "active";
}
