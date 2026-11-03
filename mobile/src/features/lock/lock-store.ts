import { useSyncExternalStore } from "react";

/** Whether the biometric lock covers the app (in memory; decided again at every start). */
let locked = false;
/**
 * The signed-in user's biometric choice, mirrored in memory so returning from the background
 * can lock synchronously - before any signed-in screen draws a frame (no Keychain round trip).
 */
let biometricOn = false;
const listeners = new Set<() => void>();

export function isLocked(): boolean {
  return locked;
}

export function setLocked(next: boolean): void {
  if (next === locked) return;
  locked = next;
  for (const listener of listeners) listener();
}

export function isBiometricOn(): boolean {
  return biometricOn;
}

export function setBiometricOn(on: boolean): void {
  biometricOn = on;
}

function subscribe(listener: () => void): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

export function useLocked(): boolean {
  return useSyncExternalStore(subscribe, isLocked, isLocked);
}
