import { createMMKV, deleteMMKV, type MMKV } from "react-native-mmkv";

import { deleteSecure, readSecure, secureKeys, writeSecure } from "@/features/auth/secure-tokens";

import { getAccessToken, getStatus, tokenSubject } from "@/features/auth/session-store";

import { randomSecret } from "./random";

/**
 * The device's encrypted store for health data kept offline: the persisted query cache and
 * the queue of writes waiting for the network (CLAUDE.md rule 8, docs/08 "Аюулгүй байдал").
 *
 * MMKV with AES-256; its id and key live in the Keychain/Keystore (secure-store, readable
 * only while the phone is unlocked, never backed up). Each new key gets a new store id, so a
 * store whose key was lost is never opened with another key. Signing out clears the store
 * and deletes the key and the store's files: anything that survived on disk could no longer
 * be decrypted, and nothing is left to.
 */

type Keyring = { id: string; key: string; account: string };

let store: MMKV | null = null;
let opening: Promise<MMKV> | null = null;
let generation = 0; // a wipe while a store is opening must win
let wiping: Promise<void> | null = null; // an open waits for a wipe still deleting the old store

function isKeyring(value: unknown): value is Keyring {
  return (
    typeof value === "object" &&
    value !== null &&
    typeof (value as Keyring).id === "string" &&
    typeof (value as Keyring).key === "string" &&
    typeof (value as Keyring).account === "string"
  );
}

async function keyring(account: string, started: number): Promise<Keyring> {
  const saved = await readSecure(secureKeys.localStore);
  if (saved) {
    let parsed: unknown = null;
    try {
      parsed = JSON.parse(saved);
    } catch {
      // unreadable: start a new store under a new key (the old one cannot be opened)
    }
    if (isKeyring(parsed) && parsed.account === account) return parsed;
    // Another account's store (a sign-out whose wipe did not finish): empty it, never open it
    // for this one.
    if (isKeyring(parsed)) {
      createMMKV({
        id: parsed.id,
        encryptionKey: parsed.key,
        encryptionType: "AES-256",
      }).clearAll();
      if (parsed.id.startsWith("lt.local.")) dropFiles(parsed.id);
    }
  }
  if (started !== generation) throw new Error("local store wiped while opening");
  // 32 characters x 6 bits = 192 bits of key material (MMKV takes the key as a string)
  const fresh = { id: `lt.local.${randomSecret(12)}`, key: randomSecret(32), account };
  await writeSecure(secureKeys.localStore, JSON.stringify(fresh));
  if (started !== generation) {
    await deleteSecure(secureKeys.localStore); // a wipe ran meanwhile: leave no keyring
    throw new Error("local store wiped while opening");
  }
  return fresh;
}

/**
 * The signed-in account's store (opened once per sign-in). Refused when nobody is signed in:
 * nothing may be queued or cached for "no one", and never into another account's store.
 */
export function localStore(): Promise<MMKV> {
  if (store) return Promise.resolve(store);
  if (!opening) {
    const started = generation;
    opening = (async () => {
      // never read a keyring a sign-out is still deleting (it would reopen a store being removed)
      if (wiping) await wiping;
      if (started !== generation) throw new Error("local store wiped while opening");
      if (getStatus() !== "signedIn") throw new Error("not signed in");
      let account = await readSecure(secureKeys.account);
      if (!account) {
        // signed in before the account was recorded: take it from the access token
        account = tokenSubject(getAccessToken());
        if (!account) throw new Error("no account");
        await writeSecure(secureKeys.account, account);
      }
      return keyring(account, started);
    })()
      .then(({ id, key }) => {
        if (started !== generation) throw new Error("local store wiped while opening");
        store = createMMKV({ id, encryptionKey: key, encryptionType: "AES-256" });
        return store;
      })
      .finally(() => {
        opening = null;
      });
  }
  return opening;
}

/** The store if it is already open - for synchronous paths (never opens it). */
export function openLocalStore(): MMKV | null {
  return store;
}

/** A store's files on disk (its data is cleared first; a failure only leaves ciphertext). */
function dropFiles(id: string): void {
  try {
    deleteMMKV(id);
  } catch {
    // still open elsewhere or already gone: the key is deleted anyway
  }
}

/** Sign-out: everything in the store, its files, then its key (crypto-shredding). */
export async function wipeLocalStore(): Promise<void> {
  generation += 1;
  const current = store;
  store = null;
  const previous = wiping;
  const run = (async () => {
    await previous?.catch(() => undefined); // a failed wipe never stops this one
    await removeStore(current);
  })();
  wiping = run;
  try {
    await run;
  } finally {
    if (wiping === run) wiping = null;
  }
}

async function removeStore(current: MMKV | null): Promise<void> {
  try {
    current?.clearAll();
    // the store this phone keeps for the account, also when it was never opened this run
    const saved = await readSecure(secureKeys.localStore);
    let id: unknown = null;
    try {
      id = saved ? (JSON.parse(saved) as { id?: unknown }).id : null;
    } catch {
      // unreadable keyring: nothing to name
    }
    if (typeof id === "string" && id.startsWith("lt.local.")) dropFiles(id);
  } finally {
    await deleteSecure(secureKeys.localStore);
  }
}
