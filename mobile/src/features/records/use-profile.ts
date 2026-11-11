import type { components } from "@labtrack/shared";
import { useMutation, useQuery } from "@tanstack/react-query";
import { deleteSnapshot, dropSnapshotsExcept } from "@/features/emergency/snapshot";
import { keepUnlockedOnly, setCardUnlocked } from "@/features/emergency/unlocked";

import { api } from "@/lib/api";
import { queryClient } from "@/lib/query-client";
import { apiError } from "@/lib/use-error-text";

export type Patient = components["schemas"]["PatientOut"];

export const patientsKey = ["patients"] as const;

const PROFILE_ID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

/**
 * Everything cached about one profile (in memory and, through the persister, in the
 * encrypted store): its queries are keyed [kind, patientId, ...]. Used when access ends -
 * the user left as caregiver, or the profile is no longer in the list (access ended, the
 * owner withdrew the sharing consent - Q42). Rule 8: no one else's data stays on the phone.
 */
export function dropProfileData(patientId: string): void {
  queryClient.removeQueries({ predicate: (q) => q.queryKey[1] === patientId });
  // and its saved emergency card / lock-screen opening, should any exist (never for another's
  // profile today - defence in depth)
  void deleteSnapshot(patientId).catch(() => undefined);
  void setCardUnlocked(patientId, false).catch(() => undefined);
}

/** After the list is read: drop what is cached for any profile not in it any more. */
export async function dropMissingProfiles(patients: readonly { id: string }[]): Promise<void> {
  const known = new Set(patients.map((p) => p.id));
  queryClient.removeQueries({
    predicate: (q) => {
      const id = q.queryKey[1];
      return typeof id === "string" && PROFILE_ID.test(id) && !known.has(id);
    },
  });
  await Promise.allSettled([dropSnapshotsExcept(known), keepUnlockedOnly(known)]);
}

/** The health profiles the user can open: their own first (GET /patients). */
export function usePatients({ enabled = true }: { enabled?: boolean } = {}) {
  return useQuery({
    queryKey: patientsKey,
    enabled,
    meta: { persist: true }, // shown offline (encrypted local store)
    queryFn: async () => {
      const { data, error } = await api.GET("/api/v1/patients");
      if (!data) throw apiError(error);
      void dropMissingProfiles(data);
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
