import { useSyncExternalStore } from "react";

/**
 * The onboarding transplant wizard stays on screen until the user finishes it - also after its
 * first save created the own profile, which would otherwise let the onboarding guard move on
 * before "Have you had another transplant?" (in memory: a restart simply ends the wizard).
 */
let active = false;
const listeners = new Set<() => void>();

export function wizardActive(): boolean {
  return active;
}

export function setWizardActive(next: boolean): void {
  if (next === active) return;
  active = next;
  for (const listener of listeners) listener();
}

function subscribe(listener: () => void): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

export function useWizardActive(): boolean {
  return useSyncExternalStore(
    subscribe,
    () => active,
    () => active,
  );
}
