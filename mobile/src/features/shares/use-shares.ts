import type { components } from "@labtrack/shared";
import { useMutation, useQuery } from "@tanstack/react-query";

import { setActiveProfile } from "@/features/records/active-profile";
import { dropProfileData } from "@/features/records/use-profile";
import { api } from "@/lib/api";
import { queryClient } from "@/lib/query-client";
import { apiError } from "@/lib/use-error-text";

/**
 * Sharing a profile by username with a doctor or a viewer (Phase 7.1; API 0040): the owner's
 * list, invitations and "who opened it"; the invited person's answers; stepping back. Nothing
 * here is kept offline: who may see a profile is always read fresh from the server.
 */

export type Shares = components["schemas"]["SharesOut"];
export type ShareView = components["schemas"]["ShareViewOut"];
export type MyShareInvitation = components["schemas"]["MyShareInvitationOut"];
export type ShareLevel = "doctor" | "viewer";
export type ShareDays = 1 | 7 | 30 | null;

const sharesKey = (patientId: string | undefined) => ["shares", patientId] as const;
const viewsKey = (patientId: string | undefined) => ["share-views", patientId] as const;
const invitationsKey = ["me", "share-invitations"] as const;

/** For the profile's owner: who has it, until when, and open invitations. */
export function useShares(patientId: string | undefined, { enabled = true } = {}) {
  return useQuery({
    queryKey: sharesKey(patientId),
    enabled: enabled && patientId !== undefined,
    staleTime: 0,
    queryFn: async () => {
      const { data, error } = await api.GET("/api/v1/patients/{patient_id}/shares", {
        params: { path: { patient_id: patientId ?? "" } },
      });
      if (!data) throw apiError(error);
      return data;
    },
  });
}

/** For the profile's owner: who opened it through a share, by day (the last 90 days). */
export function useShareViews(patientId: string | undefined, { enabled = true } = {}) {
  return useQuery({
    queryKey: viewsKey(patientId),
    enabled: enabled && patientId !== undefined,
    staleTime: 0,
    queryFn: async () => {
      const { data, error } = await api.GET("/api/v1/patients/{patient_id}/share-views", {
        params: { path: { patient_id: patientId ?? "" } },
      });
      if (!data) throw apiError(error);
      return data;
    },
  });
}

function invalidate(patientId: string) {
  void queryClient.invalidateQueries({ queryKey: sharesKey(patientId) });
  void queryClient.invalidateQueries({ queryKey: viewsKey(patientId) });
}

/** The answer is the same whoever the username is: the list shows whether it reached someone. */
export function useInviteShare(patientId: string) {
  return useMutation({
    mutationFn: async (body: { username: string; level: ShareLevel; days: ShareDays }) => {
      const { error, response } = await api.POST(
        "/api/v1/patients/{patient_id}/share-invitations",
        { params: { path: { patient_id: patientId } }, body },
      );
      if (!response.ok) throw apiError(error);
    },
    onSettled: () => invalidate(patientId),
  });
}

export function useCancelShareInvitation(patientId: string) {
  return useMutation({
    mutationFn: async (invitationId: string) => {
      const { error, response } = await api.DELETE(
        "/api/v1/patients/{patient_id}/share-invitations/{invitation_id}",
        { params: { path: { patient_id: patientId, invitation_id: invitationId } } },
      );
      if (!response.ok) throw apiError(error);
    },
    onSettled: () => invalidate(patientId),
  });
}

export function useEndShare(patientId: string) {
  return useMutation({
    mutationFn: async (userId: string) => {
      const { error, response } = await api.DELETE(
        "/api/v1/patients/{patient_id}/shares/{user_id}",
        { params: { path: { patient_id: patientId, user_id: userId } } },
      );
      if (!response.ok) throw apiError(error);
    },
    onSettled: () => invalidate(patientId),
  });
}

/** For the invited person: open invitations (who asks - no profile name before accepting). */
export function useMyShareInvitations() {
  return useQuery({
    queryKey: invitationsKey,
    staleTime: 0,
    queryFn: async () => {
      const { data, error } = await api.GET("/api/v1/me/share-invitations");
      if (!data) throw apiError(error);
      return data;
    },
  });
}

export function useRespondShare() {
  return useMutation({
    mutationFn: async (answer: { invitation_id: string; accept: boolean }) => {
      const { error, response } = await api.POST("/api/v1/me/share-invitations/respond", {
        body: answer,
      });
      if (!response.ok) throw apiError(error);
    },
    onSettled: () => {
      void queryClient.invalidateQueries({ queryKey: invitationsKey });
      // an accepted profile now appears in the list of profiles
      void queryClient.invalidateQueries({ queryKey: ["patients"] });
      void queryClient.invalidateQueries({ queryKey: ["me", "notifications"] });
    },
  });
}

/** A doctor or a viewer steps back from a profile shared with them. */
export function useLeaveShare() {
  return useMutation({
    mutationFn: async (patientId: string) => {
      const { error, response } = await api.POST("/api/v1/me/shares/leave", {
        body: { patient_id: patientId },
      });
      if (!response.ok) throw apiError(error);
    },
    onSuccess: (_, patientId) => {
      // nothing of that profile stays on this phone, and the screens go back to the own profile
      dropProfileData(patientId);
      setActiveProfile(null);
      void queryClient.invalidateQueries({ queryKey: ["me", "notifications"] });
    },
    onSettled: () => void queryClient.invalidateQueries({ queryKey: ["patients"] }),
  });
}
