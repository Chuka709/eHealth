import type { components } from "@labtrack/shared";
import { useMutation, useQuery } from "@tanstack/react-query";

import { api } from "@/lib/api";
import { queryClient } from "@/lib/query-client";
import { apiError } from "@/lib/use-error-text";

export type Patient = components["schemas"]["PatientOut"];

export const patientsKey = ["patients"] as const;

/** The health profiles the user can open: their own first (GET /patients). */
export function usePatients({ enabled = true }: { enabled?: boolean } = {}) {
  return useQuery({
    queryKey: patientsKey,
    enabled,
    meta: { persist: true }, // shown offline (encrypted local store)
    queryFn: async () => {
      const { data, error } = await api.GET("/api/v1/patients");
      if (!data) throw apiError(error);
      return data;
    },
  });
}

/** The user's own profile, once it exists. */
export function ownProfile(patients: readonly Patient[] | undefined): Patient | undefined {
  return patients?.find((p) => p.relation === "self" && p.access_level === "owner");
}

/**
 * Creates the user's own profile (named as their account) - the first step of the transplant
 * wizard, also when it is skipped: the profile is what the health records hang on.
 */
export function useCreateOwnProfile() {
  return useMutation({
    mutationFn: async (fullName: string) => {
      const { data, error, response } = await api.POST("/api/v1/patients", {
        body: { full_name: fullName, relation: "self", sex: "unknown" },
      });
      if (data) return data;
      // created by an earlier attempt whose answer was lost: that profile is the one
      if (response.status === 409 && error?.code === "patient.self_exists") {
        const listed = await api.GET("/api/v1/patients");
        const own = ownProfile(listed.data);
        if (own) return own;
      }
      throw apiError(error);
    },
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: patientsKey }),
  });
}
