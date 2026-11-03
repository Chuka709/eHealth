import * as SecureStore from "expo-secure-store";

// docs/04 §6.8: credentials live only in the Keychain/Keystore, readable while the phone is
// unlocked and never migrated to another device by a backup or a phone transfer.
const options: SecureStore.SecureStoreOptions = {
  keychainAccessible: SecureStore.WHEN_UNLOCKED_THIS_DEVICE_ONLY,
};

export const secureKeys = {
  /** Refresh token (60 days, rotated on every refresh). */
  refresh: "lt.refresh",
  /**
   * Trusted-device token (OWASP device cookie, docs/04 §1 brute-force). Kept across a normal
   * sign-out so a signed-out owner is not treated as an unknown device; the server drops the
   * trust on admin reset, disable and password change.
   */
  device: "lt.device",
  /** The notice that ended the session (admin reset, report, deletion) until it is read. */
  notice: "lt.notice",
  /** Biometric unlock choice of the signed-in user: "on" | "off" (removed on sign-out). */
  biometric: "lt.biometric",
  /**
   * Unlock key: readable only after a biometric check against the *current* enrollment (iOS
   * `.biometryCurrentSet`, Android Keystore with BIOMETRIC_STRONG, no passcode fallback). Adding
   * a finger or face invalidates it, so someone who knows the phone PIN and enrols their own
   * finger cannot open the app. The value carries no secret; the access control is the point.
   */
  unlockGate: "lt.unlock_gate",
} as const;

export type SecureKey = (typeof secureKeys)[keyof typeof secureKeys];

const GATE_VALUE = "1";

// Stricter than the other items: removed by iOS if the phone's passcode is turned off.
const gateOptions: SecureStore.SecureStoreOptions = {
  keychainAccessible: SecureStore.WHEN_PASSCODE_SET_THIS_DEVICE_ONLY,
  requireAuthentication: true,
};

/** Creates the unlock key (whether this already prompts differs by platform). */
export function writeUnlockGate(prompt: string): Promise<void> {
  return SecureStore.setItemAsync(secureKeys.unlockGate, GATE_VALUE, {
    ...gateOptions,
    authenticationPrompt: prompt,
  });
}

/**
 * Reads the unlock key behind the biometric prompt: "ok"; "invalidated" when the key is gone
 * (biometrics changed or removed — only a password sign-in may follow); "failed" on cancel or a
 * failed check (try again).
 */
export async function readUnlockGate(prompt: string): Promise<"ok" | "invalidated" | "failed"> {
  try {
    const value = await SecureStore.getItemAsync(secureKeys.unlockGate, {
      ...gateOptions,
      authenticationPrompt: prompt,
    });
    if (value === null) return "invalidated";
    return value === GATE_VALUE ? "ok" : "invalidated";
  } catch (error) {
    // A key invalidated by an enrollment change may throw instead of reading as missing
    // (Android KeyPermanentlyInvalidatedException); never let that loop as a mere failure.
    // To confirm on devices: add/remove a finger, then unlock.
    return /invalidat/i.test(String(error)) ? "invalidated" : "failed";
  }
}

export function readSecure(key: SecureKey): Promise<string | null> {
  return SecureStore.getItemAsync(key, options);
}

export function writeSecure(key: SecureKey, value: string): Promise<void> {
  return SecureStore.setItemAsync(key, value, options);
}

export async function deleteSecure(...keys: SecureKey[]): Promise<void> {
  await Promise.all(keys.map((key) => SecureStore.deleteItemAsync(key, options)));
}
