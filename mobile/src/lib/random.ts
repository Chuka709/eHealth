import * as Crypto from "expo-crypto";

/**
 * Client-made ids for records written from this device (transplants, medications, intakes):
 * the server stores one row per client_id, so a retried or queued request never duplicates.
 */
export function newClientId(): string {
  return Crypto.randomUUID();
}

const ALPHABET = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_";

/** A random secret from the platform's CSPRNG, as URL-safe text (6 bits per character). */
export function randomSecret(length = 32): string {
  const bytes = Crypto.getRandomBytes(length);
  let out = "";
  for (const byte of bytes) out += ALPHABET[byte & 63];
  return out;
}
