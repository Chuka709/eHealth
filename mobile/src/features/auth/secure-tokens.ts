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
  /** Set when an admin reset ended the session; cleared once the user has seen the notice. */
  adminResetNotice: "lt.admin_reset",
  /** Biometric unlock choice of the signed-in user: "on" | "off" (removed on sign-out). */
  biometric: "lt.biometric",
} as const;

export type SecureKey = (typeof secureKeys)[keyof typeof secureKeys];

export function readSecure(key: SecureKey): Promise<string | null> {
  return SecureStore.getItemAsync(key, options);
}

export function writeSecure(key: SecureKey, value: string): Promise<void> {
  return SecureStore.setItemAsync(key, value, options);
}

export async function deleteSecure(...keys: SecureKey[]): Promise<void> {
  await Promise.all(keys.map((key) => SecureStore.deleteItemAsync(key, options)));
}
