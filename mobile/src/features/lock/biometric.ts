import { useQuery } from "@tanstack/react-query";
import * as LocalAuthentication from "expo-local-authentication";

import {
  deleteSecure,
  readSecure,
  readUnlockGate,
  secureKeys,
  writeSecure,
  writeUnlockGate,
} from "@/features/auth/secure-tokens";
import { queryClient } from "@/lib/query-client";

import { setBiometricOn } from "./lock-store";

export type BiometricChoice = "on" | "off";

/** Background time after which the app asks to unlock again (docs/04 §1). */
export const LOCK_AFTER_MINUTES = 5;

const biometricKey = ["device", "biometric"] as const;

/** Whether the phone can do strong biometrics (hardware present and a finger/face enrolled). */
export async function biometricAvailable(): Promise<boolean> {
  try {
    // Strong (class 3) only: weak camera face unlock would be offered but then always fail
    // the "strong" prompt below.
    return (
      (await LocalAuthentication.hasHardwareAsync()) &&
      (await LocalAuthentication.getEnrolledLevelAsync()) >=
        LocalAuthentication.SecurityLevel.BIOMETRIC_STRONG
    );
  } catch {
    return false;
  }
}

/**
 * Biometric unlock: on, off (declined or turned off), or not chosen yet. The offer is shown once
 * after the first consents, only on phones that can do it.
 */
export function useBiometricState() {
  return useQuery({
    queryKey: biometricKey,
    queryFn: async () => {
      const choice = (await readSecure(secureKeys.biometric).catch(
        () => null,
      )) as BiometricChoice | null;
      return { choice, available: await biometricAvailable() };
    },
    staleTime: Number.POSITIVE_INFINITY,
  });
}

/**
 * Turns biometric unlock on: creates the unlock key bound to the current biometric enrollment
 * and proves it opens by reading it back. No passcode
 * fallback - the threat model counts family members, who may know the phone PIN (1.11 plan).
 * On cancel or failure nothing stays behind.
 */
export async function enableBiometricLock(prompt: string): Promise<boolean> {
  try {
    await writeUnlockGate(prompt);
    // Read back on every platform: "on" only once the key is proven to open (some Android
    // versions may not prompt on write).
    if ((await readUnlockGate(prompt)) !== "ok") {
      await deleteSecure(secureKeys.unlockGate);
      return false;
    }
    await setBiometricChoice("on");
    setBiometricOn(true);
    return true;
  } catch {
    await deleteSecure(secureKeys.unlockGate).catch(() => undefined);
    return false;
  }
}

/** "Not now" in the offer, or turning it off later: the unlock key goes too. */
export async function disableBiometricLock(): Promise<void> {
  setBiometricOn(false);
  await deleteSecure(secureKeys.unlockGate);
  await setBiometricChoice("off");
}

async function setBiometricChoice(choice: BiometricChoice): Promise<void> {
  await writeSecure(secureKeys.biometric, choice);
  await queryClient.invalidateQueries({ queryKey: biometricKey });
}
