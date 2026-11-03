import { useSyncExternalStore } from "react";

/**
 * A notice that ended the session and must be seen before anything else: an admin reset
 * (docs/04 §1 step 5a), the user's own "Би хүсээгүй" report, or an account deletion request.
 * It survives an app restart (secure-store) until the user moves on.
 */
export type Notice =
  | { kind: "adminReset" }
  | { kind: "reported" }
  | { kind: "deleted"; scheduledFor: string };

let current: Notice | null = null;
const listeners = new Set<() => void>();

export function getNotice(): Notice | null {
  return current;
}

export function setNotice(next: Notice | null): void {
  current = next;
  for (const listener of listeners) listener();
}

const subscribe = (listener: () => void) => {
  listeners.add(listener);
  return () => listeners.delete(listener);
};

export function useNotice(): Notice | null {
  return useSyncExternalStore(subscribe, getNotice, getNotice);
}

/** Parses a stored notice; anything unexpected is dropped (never trusted as UI text). */
export function parseNotice(raw: string | null): Notice | null {
  if (!raw) return null;
  try {
    const value: unknown = JSON.parse(raw);
    if (typeof value !== "object" || value === null || !("kind" in value)) return null;
    if (value.kind === "adminReset" || value.kind === "reported") return { kind: value.kind };
    if (
      value.kind === "deleted" &&
      "scheduledFor" in value &&
      typeof value.scheduledFor === "string" &&
      !Number.isNaN(Date.parse(value.scheduledFor))
    ) {
      return { kind: "deleted", scheduledFor: value.scheduledFor };
    }
  } catch {
    // fall through
  }
  return null;
}
