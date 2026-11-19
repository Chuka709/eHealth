import { useMutation, useQuery } from "@tanstack/react-query";

import { queryClient } from "@/lib/query-client";

import { type EmergencyCard, readSnapshot } from "./snapshot";
import { answerCardOffer, cardOfferAnswered, setCardUnlocked, unlockedProfiles } from "./unlocked";

const unlockedKey = ["emergency-unlocked"] as const;
const offerKey = ["emergency-offer"] as const;

/** The profiles whose card the locked app may show (a device setting, off by default). */
export function useUnlockedProfiles() {
  return useQuery({ queryKey: unlockedKey, queryFn: unlockedProfiles, staleTime: 0 });
}

export function useSetCardUnlocked() {
  return useMutation({
    mutationFn: ({ patientId, on }: { patientId: string; on: boolean }) =>
      setCardUnlocked(patientId, on),
    onSettled: () => void queryClient.invalidateQueries({ queryKey: unlockedKey }),
  });
}

/** Whether to show the one-time offer: never answered before. */
export function useCardOffer() {
  const answered = useQuery({ queryKey: offerKey, queryFn: cardOfferAnswered });
  const answer = useMutation({
    mutationFn: answerCardOffer,
    onSettled: () => void queryClient.invalidateQueries({ queryKey: offerKey }),
  });
  return { show: answered.data === false, answer };
}

/**
 * For the lock screen: the saved cards of the profiles the user allowed, read from the
 * encrypted store only. No API call is made and nothing signed-in is mounted (H22). Not
 * cached: read each time the lock screen opens, so a setting turned off or a card dropped
 * meanwhile is never shown.
 */
export type LockedCard = { id: string; card: EmergencyCard };

export async function lockedCards(): Promise<LockedCard[]> {
  const ids = await unlockedProfiles();
  const cards = await Promise.all(ids.map(async (id) => ({ id, card: await readSnapshot(id) })));
  return cards.filter((c): c is LockedCard => c.card !== null);
}
