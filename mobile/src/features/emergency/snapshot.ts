import type { components } from "@labtrack/shared";

import { currentEpoch, isWiping } from "@/features/auth/session";
import { getStatus } from "@/features/auth/session-store";
import { localStore, openLocalStore } from "@/lib/local-store";
import { healthDropCount, SNAPSHOT_PREFIX } from "@/lib/persist";

export type EmergencyCard = components["schemas"]["EmergencyCardOut"];

/**
 * The emergency card's offline copy (docs/08, H17): the last card the server sent, kept in the
 * encrypted local store. It is kept apart from the query cache for three reasons:
 * - it is never dropped for being a week old (the card must open offline after a long trip);
 * - one card can be read without restoring the whole cache (2.7c: the locked app shows only
 *   this);
 * - it can be deleted on its own when access to the profile ends.
 *
 * Sign-out clears the whole store and its key. A withdrawn consent drops every snapshot
 * (`dropPersistedHealthData`).
 */

const VERSION = "v1"; // bump when the card's shape changes: an older copy is then ignored
const key = (patientId: string) => `${SNAPSHOT_PREFIX}emergency-card.${VERSION}.${patientId}`;

function isCard(value: unknown): value is EmergencyCard {
  if (typeof value !== "object" || value === null) return false;
  const card = value as Record<string, unknown>;
  return (
    typeof card.generated_at === "string" &&
    typeof card.patient === "object" &&
    card.patient !== null &&
    ["transplants", "dosed_medications", "other_medications", "allergies", "contacts"].every(
      (part) => Array.isArray(card[part]),
    )
  );
}

/** The saved card, or null: none saved, unreadable, or nobody signed in. */
export async function readSnapshot(patientId: string): Promise<EmergencyCard | null> {
  const drops = healthDropCount();
  try {
    const store = await localStore();
    // a consent withdrawn while the store was opening: what is read may be about to go
    if (healthDropCount() !== drops) return null;
    const raw = store.getString(key(patientId));
    if (!raw) return null;
    const parsed: unknown = JSON.parse(raw);
    return isCard(parsed) ? parsed : null;
  } catch {
    return null; // a copy that cannot be read is no copy (never a half-shown card)
  }
}

/**
 * Taken before the card is fetched. A save may follow only if nothing ended in between:
 * no sign-out or new sign-in (epoch, store), and no consent withdrawn (drop count). Otherwise
 * an answer that arrives late would write the card back, possibly into the next account's
 * store.
 */
export type SaveTicket = { epoch: number; drops: number; store: ReturnType<typeof openLocalStore> };

export async function saveTicket(): Promise<SaveTicket> {
  const store = await localStore().catch(() => null);
  return { epoch: currentEpoch(), drops: healthDropCount(), store };
}

export function stillValid(ticket: SaveTicket): boolean {
  return (
    ticket.store !== null &&
    openLocalStore() === ticket.store &&
    currentEpoch() === ticket.epoch &&
    healthDropCount() === ticket.drops &&
    !isWiping() &&
    getStatus() === "signedIn"
  );
}

/** Saves the card, only if the ticket is still valid. Returns whether it was saved. */
export function saveSnapshot(ticket: SaveTicket, patientId: string, card: EmergencyCard): boolean {
  if (!stillValid(ticket) || !ticket.store) return false;
  ticket.store.set(key(patientId), JSON.stringify(card));
  return true;
}

/** Access to the profile ended (or its consents): its copy leaves the phone. */
export async function deleteSnapshot(patientId: string): Promise<void> {
  try {
    (await localStore()).remove(key(patientId));
  } catch {
    // signed out: the store and its key are already gone
  }
}
