import { useQuery } from "@tanstack/react-query";

import { api } from "@/lib/api";
import { queryClient } from "@/lib/query-client";
import { ApiError, apiError } from "@/lib/use-error-text";

import {
  deleteSnapshot,
  type EmergencyCard,
  readSnapshot,
  saveSnapshot,
  saveTicket,
  stillValid,
} from "./snapshot";

export const emergencyCardKey = (patientId: string) => ["emergency-card", patientId] as const;
const savedKey = (patientId: string) => ["emergency-card", patientId, "saved"] as const;

/** The server no longer lets this user read the profile (access ended, consents withdrawn).
 * A marked ApiError, not a subclass: `instanceof` on a transpiled Error subclass is unreliable. */
const ended = new WeakSet<Error>();
const accessEnded = (error: unknown) => error instanceof Error && ended.has(error);
// when access to a profile last ended: a card fetched before it is never shown again, even if
// a later retry fails for another reason (offline) and the query still holds the old data
const endedAt = new Map<string, number>();

/**
 * The emergency card of a profile: the server's card when it can be reached (saved as the
 * offline copy), otherwise the saved copy, marked with the time the server made it. The card
 * is always the one the server assembled (api/emergency_card.py); the app only shows it.
 *
 * When access to the profile ends (404, 403), the copy is deleted and nothing is shown, not
 * even a card already in memory. An unreachable server never deletes it. Both queries are
 * `meta.snapshot`: a withdrawn consent removes them from memory with the cache.
 */
export function useEmergencyCard(patientId: string | undefined) {
  const id = patientId ?? "";
  const saved = useQuery({
    queryKey: savedKey(id),
    enabled: Boolean(patientId),
    staleTime: Number.POSITIVE_INFINITY,
    meta: { snapshot: true },
    queryFn: () => readSnapshot(id),
  });
  const live = useQuery({
    queryKey: emergencyCardKey(id),
    enabled: Boolean(patientId),
    // never `meta.persist`: the snapshot is the offline copy (no second copy in the cache)
    meta: { snapshot: true },
    queryFn: async ({ signal }): Promise<EmergencyCard> => {
      const ticket = await saveTicket();
      const { data, error, response } = await api.GET(
        "/api/v1/patients/{patient_id}/emergency-card",
        { params: { path: { patient_id: id } }, signal },
      );
      // signed out, another account, or a consent withdrawn meanwhile: keep nothing
      if (!stillValid(ticket)) throw new Error("session changed");
      if (data) {
        if (saveSnapshot(ticket, id, data)) queryClient.setQueryData(savedKey(id), data);
        return data;
      }
      if (response.status === 404 || response.status === 403) {
        await deleteSnapshot(id);
        queryClient.setQueryData(savedKey(id), null);
        endedAt.set(id, Date.now());
        const gone = apiError(error);
        ended.add(gone);
        throw gone;
      }
      throw apiError(error);
    },
    retry: (failures, error) => !(error instanceof ApiError) && failures < 1,
  });
  // a failed refetch keeps the last data: after an access loss it must not stay on screen
  const current = live.data && live.dataUpdatedAt > (endedAt.get(id) ?? 0) ? live.data : undefined;
  const card = accessEnded(live.error) ? undefined : (current ?? saved.data ?? undefined);
  return {
    card,
    /** The server could not be reached just now: the card shown may be out of date. */
    offline: Boolean(card) && live.isError,
    loading: Boolean(patientId) && !card && !live.isError && (live.isPending || saved.isPending),
    error: card ? null : live.error,
    refetch: () => void live.refetch(),
  };
}
