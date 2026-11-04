import type { components } from "@labtrack/shared";
import { useMutation, useQuery } from "@tanstack/react-query";

import { api } from "@/lib/api";
import { queryClient } from "@/lib/query-client";
import { apiError } from "@/lib/use-error-text";

export type Transplant = components["schemas"]["TransplantOut"];
export type TransplantFields = components["schemas"]["TransplantIn"];
type TransplantCreate = components["schemas"]["TransplantCreate"];

export const transplantsKey = (patientId: string) => ["transplants", patientId] as const;

/** `fresh`: refetch on mount - an edit form must start from the server's current record. */
export function useTransplants(patientId: string | undefined, { fresh = false } = {}) {
  return useQuery({
    queryKey: transplantsKey(patientId ?? ""),
    enabled: Boolean(patientId),
    refetchOnMount: fresh ? "always" : true,
    meta: { persist: true },
    queryFn: async () => {
      const { data, error } = await api.GET("/api/v1/patients/{patient_id}/transplants", {
        params: { path: { patient_id: patientId ?? "" } },
      });
      if (!data) throw apiError(error);
      return data;
    },
  });
}

const refresh = (patientId: string) =>
  void queryClient.invalidateQueries({ queryKey: transplantsKey(patientId) });

/** POST with the form's client_id: a retried save finds the stored record (no duplicate). */
export function useCreateTransplant() {
  return useMutation({
    mutationFn: async ({ patientId, body }: { patientId: string; body: TransplantCreate }) => {
      const { data, error } = await api.POST("/api/v1/patients/{patient_id}/transplants", {
        params: { path: { patient_id: patientId } },
        body,
      });
      if (!data) throw apiError(error);
      return data;
    },
    onSuccess: (_, { patientId }) => refresh(patientId),
  });
}

export function useUpdateTransplant(patientId: string, transplantId: string) {
  return useMutation({
    mutationFn: async (body: TransplantFields) => {
      const { data, error } = await api.PUT(
        "/api/v1/patients/{patient_id}/transplants/{transplant_id}",
        { params: { path: { patient_id: patientId, transplant_id: transplantId } }, body },
      );
      if (!data) throw apiError(error);
      return data;
    },
    onSuccess: () => refresh(patientId),
  });
}

export function useDeleteTransplant(patientId: string, transplantId: string) {
  return useMutation({
    mutationFn: async () => {
      const { error, response } = await api.DELETE(
        "/api/v1/patients/{patient_id}/transplants/{transplant_id}",
        { params: { path: { patient_id: patientId, transplant_id: transplantId } } },
      );
      if (!response.ok) throw apiError(error);
    },
    onSuccess: () => refresh(patientId),
  });
}
