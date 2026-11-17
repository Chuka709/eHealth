import type { components } from "@labtrack/shared";
import { useMutation, useQuery } from "@tanstack/react-query";

import { api } from "@/lib/api";
import { queryClient } from "@/lib/query-client";
import { apiError } from "@/lib/use-error-text";

/**
 * A treating doctor's targets and notes on a profile, and the tacrolimus level statistics
 * (Phase 7.6 over the 7.4 API). Everyone who can read the profile reads them; only a doctor the
 * owner shared it with writes them (the server decides). Numbers stay strings (rule 7); the app
 * computes nothing (rule 6). Read fresh, never kept offline.
 */

export type Target = components["schemas"]["TargetOut"];
export type DoctorNote = components["schemas"]["NoteOut"];
export type LevelStats = components["schemas"]["LevelStatsOut"];

const targetsKey = (p: string | undefined) => ["targets", p] as const;
const notesKey = (p: string | undefined) => ["doctor-notes", p] as const;

export function useTargets(patientId: string | undefined) {
  return useQuery({
    queryKey: targetsKey(patientId),
    enabled: patientId !== undefined,
    staleTime: 0,
    queryFn: async () => {
      const { data, error } = await api.GET("/api/v1/patients/{patient_id}/targets", {
        params: { path: { patient_id: patientId ?? "" } },
      });
      if (!data) throw apiError(error);
      return data;
    },
  });
}

export function useDoctorNotes(patientId: string | undefined) {
  return useQuery({
    queryKey: notesKey(patientId),
    enabled: patientId !== undefined,
    staleTime: 0,
    queryFn: async () => {
      const { data, error } = await api.GET("/api/v1/patients/{patient_id}/doctor-notes", {
        params: { path: { patient_id: patientId ?? "" } },
      });
      if (!data) throw apiError(error);
      return data;
    },
  });
}

export function useLevelStats(patientId: string | undefined, testCode: string, months: number) {
  return useQuery({
    queryKey: ["level-stats", patientId, testCode, months],
    enabled: patientId !== undefined,
    staleTime: 0,
    queryFn: async () => {
      const { data, error } = await api.GET(
        "/api/v1/patients/{patient_id}/level-stats/{test_code}",
        {
          params: {
            path: { patient_id: patientId ?? "", test_code: testCode },
            query: { months },
          },
        },
      );
      if (!data) throw apiError(error);
      return data;
    },
  });
}

function refresh(patientId: string) {
  void queryClient.invalidateQueries({ queryKey: targetsKey(patientId) });
  void queryClient.invalidateQueries({ queryKey: notesKey(patientId) });
  void queryClient.invalidateQueries({ queryKey: ["level-stats", patientId] });
}

/** A decimal comma ("12,4") is read as a point; the server parses and checks the number. */
const number = (raw: string): string | null => {
  const v = raw.trim().replace(",", ".");
  return v === "" ? null : v;
};

export function useSetTarget(patientId: string) {
  return useMutation({
    mutationFn: async (input: {
      test_code: string;
      low: string;
      high: string;
      valid_from: string;
      note: string;
    }) => {
      const { error, response } = await api.POST("/api/v1/me/doctor/targets", {
        body: {
          patient_id: patientId,
          test_code: input.test_code,
          low: number(input.low),
          high: number(input.high),
          valid_from: input.valid_from,
          note: input.note.trim() || null,
        },
      });
      if (!response.ok) throw apiError(error);
    },
    onSettled: () => refresh(patientId),
  });
}

export function useEndTarget(patientId: string) {
  return useMutation({
    mutationFn: async (input: { target_id: string; on: string }) => {
      const { error, response } = await api.POST("/api/v1/me/doctor/targets/end", {
        body: input,
      });
      if (!response.ok) throw apiError(error);
    },
    onSettled: () => refresh(patientId),
  });
}

export function useAddNote(patientId: string) {
  return useMutation({
    mutationFn: async (body: string) => {
      const { error, response } = await api.POST("/api/v1/me/doctor/notes", {
        body: { patient_id: patientId, body: body.trim() },
      });
      if (!response.ok) throw apiError(error);
    },
    onSettled: () => refresh(patientId),
  });
}

export function useRemoveNote(patientId: string) {
  return useMutation({
    mutationFn: async (noteId: string) => {
      const { error, response } = await api.POST("/api/v1/me/doctor/notes/remove", {
        body: { note_id: noteId },
      });
      if (!response.ok) throw apiError(error);
    },
    onSettled: () => refresh(patientId),
  });
}
