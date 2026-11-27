import { useRef, useSyncExternalStore } from "react";

import { openLocalStore } from "@/lib/local-store";

import { ownProfile, type Patient } from "./use-profile";

/**
 * The profile the record screens show (Phase 2.8f-2, profile picker): the user's own by
 * default, or one they care for. Kept in the encrypted local store, so it is this account's
 * (another account on the phone, or a sign-out, starts from its own profile again).
 *
 * Only the record screens follow it (medicines, transplants, health records). Local reminders,
 * the emergency card, onboarding and the time zone stay the user's own (decisions 1 and 2):
 * this phone never reminds about, or shows on its lock screen, someone else's medicines.
 */

const KEY = "prefs.active_profile.v1";
const listeners = new Set<() => void>();
let selected: string | null | undefined; // undefined: not read from the store yet

function current(): string | null {
  if (selected === undefined) {
    const store = openLocalStore();
    if (!store) return null; // not open yet: the own profile until it is
    selected = store.getString(KEY) ?? null;
  }
  return selected;
}

function subscribe(listener: () => void): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

export function setActiveProfile(id: string | null): void {
  selected = id;
  const store = openLocalStore();
  if (id === null) store?.remove(KEY);
  else store?.set(KEY, id);
  for (const listener of listeners) listener();
}

/** Sign-out / another account: nothing carried over (the store itself is wiped too). */
export function resetActiveProfile(): void {
  selected = undefined;
  for (const listener of listeners) listener();
}

/** The chosen profile if the user can still open it, else their own (access ended, deleted). */
export function chooseProfile(
  patients: readonly Patient[] | undefined,
  id: string | null,
): Patient | undefined {
  return (id ? patients?.find((p) => p.id === id) : undefined) ?? ownProfile(patients);
}

export function useActiveProfile(patients: readonly Patient[] | undefined): Patient | undefined {
  const id = useSyncExternalStore(subscribe, current, () => null);
  return chooseProfile(patients, id);
}

/** Whether this is not the user's own profile (a child's, or someone cared for): the screens
 * say whose it is. */
export function isOthers(
  patient: Patient | undefined,
  patients: readonly Patient[] | undefined,
): boolean {
  return patient !== undefined && patient.id !== ownProfile(patients)?.id;
}

/**
 * A form keeps the profile it was opened on (2.8f-2 review HIGH-3): if the active profile
 * changes meanwhile (a switch, access ended and the own profile took over), `changed` is set
 * and nothing may be saved - an entry never lands on another person's profile.
 */
export function usePinnedProfile(active: Patient | undefined): {
  pinned: Patient | undefined;
  changed: boolean;
} {
  const first = useRef<string | null>(null);
  if (first.current === null && active) first.current = active.id;
  const changed = first.current !== null && active?.id !== first.current;
  return { pinned: changed ? undefined : active, changed };
}
