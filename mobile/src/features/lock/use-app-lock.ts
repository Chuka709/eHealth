import { useEffect } from "react";
import { AppState } from "react-native";

import { getStatus } from "@/features/auth/session-store";
import { queryClient } from "@/lib/query-client";

import { LOCK_AFTER_MINUTES } from "./biometric";
import { isBiometricOn, setLocked } from "./lock-store";

const LOCK_AFTER_MS = LOCK_AFTER_MINUTES * 60_000;

/**
 * Clocks for the background timer (replaceable in tests). `wall` can be set back by whoever
 * holds the phone; `mono` (performance.now) cannot, but may pause while the phone sleeps.
 * Taking the larger of the two covers both (device behaviour to confirm on real phones).
 */
export const lockClock = {
  wall: () => Date.now(),
  mono: () => globalThis.performance?.now() ?? Date.now(),
};

export interface ClockReading {
  wall: number;
  mono: number;
}

/**
 * Lock again after more than LOCK_AFTER_MINUTES in the background (docs/04 §1). A wall clock
 * that went backwards locks (fail closed).
 */
export function shouldLockOnReturn(from: ClockReading, to: ClockReading): boolean {
  const wall = to.wall - from.wall;
  if (wall < 0) return true;
  return Math.max(wall, to.mono - from.mono) >= LOCK_AFTER_MS;
}

const read = (): ClockReading => ({ wall: lockClock.wall(), mono: lockClock.mono() });

/**
 * Decides synchronously on return (the choice is mirrored in memory), so the lock is in place
 * before any signed-in screen draws or refetches. Cold starts are locked by restoreSession.
 */
export function useAppLock(): void {
  useEffect(() => {
    let backgroundAt: ClockReading | null = null;
    const subscription = AppState.addEventListener("change", (state) => {
      if (state === "background") {
        backgroundAt = read();
        return;
      }
      if (state !== "active" || backgroundAt === null) return;
      const since = backgroundAt;
      backgroundAt = null;
      if (getStatus() !== "signedIn" || !isBiometricOn()) return;
      if (!shouldLockOnReturn(since, read())) return;
      setLocked(true);
      void queryClient.cancelQueries();
    });
    return () => subscription.remove();
  }, []);
}
