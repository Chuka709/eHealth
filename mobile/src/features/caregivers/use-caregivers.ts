import type { components } from "@labtrack/shared";
import { useMutation, useQuery } from "@tanstack/react-query";

import { setActiveProfile } from "@/features/records/active-profile";
import { dropProfileData } from "@/features/records/use-profile";
import { api } from "@/lib/api";
import { queryClient } from "@/lib/query-client";
import { apiError } from "@/lib/use-error-text";

/**
 * Caregivers (Phase 2.8f-3; API 2.8d): the owner's list and invitations, the invited person's
 * answers, a caregiver's own alert settings. Nothing here is kept offline: who may see a
 * profile is always read fresh from the server.
 */

export type Caregivers = components["schemas"]["CaregiversOut"];
export type MyInvitation = components["schemas"]["MyInvitationOut"];
export type Alerts = components["schemas"]["AlertsOut"];

const caregiversKey = (patientId: string | undefined) => ["caregivers", patientId] as const;
const invitationsKey = ["me", "caregiver-invitations"] as const;
const alertsKey = (patientId: string | undefined) => ["caregiver-alerts", patientId] as const;

/** For the profile's owner: its caregivers and open invitations. */
export function useCaregivers(patientId: string | undefined, { enabled = true } = {}) {
  return useQuery({
    queryKey: caregiversKey(patientId),
    enabled: enabled && patientId !== undefined,
    queryFn: async () => {
      const { data, error } = await api.GET("/api/v1/patients/{patient_id}/caregivers", {
        params: { path: { patient_id: patientId ?? "" } },
      });
      if (!data) throw apiError(error);
      return data;
    },
  });
}

/** Whether some caregiver gets dose alerts for this profile (the owner is told when a change
 * stops them - a medicine's reminders switched off). */
export function alertingCaregivers(list: Caregivers | undefined): number {
  return (list?.caregivers ?? []).filter((c) => c.missed_dose_after_min !== null && !c.owner_paused)
    .length;
}

function invalidate(patientId: string) {
  void queryClient.invalidateQueries({ queryKey: caregiversKey(patientId) });
}

/** The answer is the same whoever the username is (2.8d): the list shows whether it reached
 * someone. */
export function useInvite(patientId: string) {
  return useMutation({
    mutationFn: async (username: string) => {
      const { error, response } = await api.POST(
        "/api/v1/patients/{patient_id}/caregiver-invitations",
        { params: { path: { patient_id: patientId } }, body: { username } },
      );
      if (!response.ok) throw apiError(error);
    },
    onSettled: () => invalidate(patientId),
  });
}

export function useCancelInvitation(patientId: string) {
  return useMutation({
    mutationFn: async (invitationId: string) => {
      const { error, response } = await api.DELETE(
        "/api/v1/patients/{patient_id}/caregiver-invitations/{invitation_id}",
        { params: { path: { patient_id: patientId, invitation_id: invitationId } } },
      );
      if (!response.ok) throw apiError(error);
    },
    onSettled: () => invalidate(patientId),
  });
}

export function useEndAccess(patientId: string) {
  return useMutation({
    mutationFn: async (userId: string) => {
      const { error, response } = await api.DELETE(
        "/api/v1/patients/{patient_id}/caregivers/{user_id}",
        { params: { path: { patient_id: patientId, user_id: userId } } },
      );
      if (!response.ok) throw apiError(error);
    },
    onSettled: () => invalidate(patientId),
  });
}

export function usePause(patientId: string) {
  return useMutation({
    mutationFn: async ({ userId, paused }: { userId: string; paused: boolean }) => {
      const { error, response } = await api.PUT(
        "/api/v1/patients/{patient_id}/caregivers/{user_id}/pause",
        { params: { path: { patient_id: patientId, user_id: userId } }, body: { paused } },
      );
      if (!response.ok) throw apiError(error);
    },
    onSettled: () => invalidate(patientId),
  });
}

/** For the invited person: open invitations (who asks - no profile name before accepting). */
export function useMyInvitations() {
  return useQuery({
    queryKey: invitationsKey,
    staleTime: 0,
    queryFn: async () => {
      const { data, error } = await api.GET("/api/v1/me/caregiver-invitations");
      if (!data) throw apiError(error);
      return data;
    },
  });
}

export function useRespond() {
  return useMutation({
    mutationFn: async (answer: { invitation_id: string; accept: boolean }) => {
      const { error, response } = await api.POST("/api/v1/me/caregiver-invitations/respond", {
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

/** For a caregiver: their own alert settings for this profile. */
export function useAlerts(patientId: string | undefined) {
  return useQuery({
    queryKey: alertsKey(patientId),
    enabled: patientId !== undefined,
    queryFn: async () => {
      const { data, error } = await api.GET("/api/v1/patients/{patient_id}/caregiver-alerts", {
        params: { path: { patient_id: patientId ?? "" } },
      });
      if (!data) throw apiError(error);
      return data;
    },
  });
}

export function useSetAlerts(patientId: string) {
  return useMutation({
    mutationFn: async (body: {
      missed_dose_after_min: number | null;
      critical_result: boolean;
    }) => {
      const { data, error } = await api.PUT("/api/v1/patients/{patient_id}/caregiver-alerts", {
        params: { path: { patient_id: patientId } },
        body,
      });
      if (!data) throw apiError(error);
      return data;
    },
    onSuccess: (data) => queryClient.setQueryData(alertsKey(patientId), data),
  });
}

export function useLeave(patientId: string) {
  return useMutation({
    mutationFn: async () => {
      const { error, response } = await api.POST("/api/v1/patients/{patient_id}/leave", {
        params: { path: { patient_id: patientId } },
      });
      if (!response.ok) throw apiError(error);
    },
    onSuccess: () => {
      // nothing of that person stays on this phone, and the screens go back to the own profile
      dropProfileData(patientId);
      setActiveProfile(null);
      void queryClient.invalidateQueries({ queryKey: ["me", "notifications"] });
    },
    onSettled: () => void queryClient.invalidateQueries({ queryKey: ["patients"] }),
  });
}
