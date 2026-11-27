import { useEffect } from "react";

import { useOwnProfile } from "@/features/health/record-screens";
import { queryClient } from "@/lib/query-client";

import { clearExportsOnce } from "./export-files";
import { emergencyCardKey, useEmergencyCard } from "./use-emergency-card";

/**
 * Keeps the own profile's saved card current (H17): fetched whenever the signed-in, unlocked app
 * runs, and again after any successful write (a dose change, a new allergy). The card the
 * locked app or an offline phone shows is then the latest the phone could get, not the one
 * from the last time the user happened to open the card. Mounted once, past the consent guard
 * and the lock (MainLayout).
 */
export function useEmergencyCardSync(): void {
  const { own } = useOwnProfile();
  useEmergencyCard(own?.id);
  const id = own?.id;
  // files exported in an earlier run (the share sheet is long closed); once per process
  useEffect(() => clearExportsOnce(), []);
  useEffect(() => {
    if (!id) return;
    return queryClient.getMutationCache().subscribe((event) => {
      if (event.type === "updated" && event.mutation.state.status === "success") {
        void queryClient.invalidateQueries({ queryKey: emergencyCardKey(id), exact: true });
      }
    });
  }, [id]);
}
