import { useQuery } from "@tanstack/react-query";
import * as LocalAuthentication from "expo-local-authentication";

import { deleteSecure, readSecure, secureKeys, writeSecure } from "@/features/auth/secure-tokens";
import { queryClient } from "@/lib/query-client";

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
 * Confirms once with the phone's biometrics, without the passcode fallback: the threat model
 * counts family members, who may know the phone PIN (decided in the 1.11 plan). On cancel or
 * failure nothing is stored.
 */
export async function authenticate(promptMessage: string, cancelLabel: string): Promise<boolean> {
  try {
    const result = await LocalAuthentication.authenticateAsync({
      promptMessage,
      cancelLabel,
      disableDeviceFallback: true,
      fallbackLabel: "",
      biometricsSecurityLevel: "strong",
    });
    return result.success;
  } catch {
    return false;
  }
}

export async function setBiometricChoice(choice: BiometricChoice): Promise<void> {
  await writeSecure(secureKeys.biometric, choice);
  await queryClient.invalidateQueries({ queryKey: biometricKey });
}

export async function clearBiometricChoice(): Promise<void> {
  await deleteSecure(secureKeys.biometric);
}
