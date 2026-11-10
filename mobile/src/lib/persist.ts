import { createAsyncStoragePersister } from "@tanstack/query-async-storage-persister";
import { persistQueryClient } from "@tanstack/react-query-persist-client";

import { localStore, openLocalStore } from "./local-store";
import { queryClient } from "./query-client";

/**
 * The query cache, kept in the encrypted local store so the app shows the user's records
 * offline (docs/08). Opt-in per query - `meta: { persist: true }` - so account and session
 * data are never written to disk; health-data queries opt in as they are added.
 */

const CACHE_KEY = "query-cache";
// Bump when a persisted query's shape changes: an older cache is then dropped, not misread.
const CACHE_VERSION = "1";
const MAX_AGE_MS = 7 * 24 * 60 * 60 * 1000;

let stop: (() => void) | null = null;
let starting: Promise<void> | null = null;
let generation = 0;

/** Restore the saved cache and keep saving it (signed in and unlocked only). */
export function startCachePersistence(): Promise<void> {
  if (stop) return Promise.resolve();
  starting ??= start().finally(() => {
    starting = null;
  });
  return starting;
}

async function start(): Promise<void> {
  const started = generation;
  const store = await localStore();
  if (started !== generation) return; // stopped while the store was opening
  let live = true; // a throttled write that lands after stop/wipe writes nothing
  // MMKV is synchronous; the persister's storage contract is async
  const persister = createAsyncStoragePersister({
    key: CACHE_KEY,
    throttleTime: 1000,
    storage: {
      getItem: async (key) => (live ? (store.getString(key) ?? null) : null),
      setItem: async (key, value) => {
        if (live) store.set(key, value);
      },
      removeItem: async (key) => {
        store.remove(key);
      },
    },
  });
  const [unsubscribe, restored] = persistQueryClient({
    queryClient,
    persister,
    maxAge: MAX_AGE_MS,
    buster: CACHE_VERSION,
    dehydrateOptions: {
      shouldDehydrateQuery: (query) =>
        query.state.status === "success" && query.meta?.persist === true,
      // never mutations: a paused one holds its variables (a password change, a record) -
      // offline writes go through the queue only
      shouldDehydrateMutation: () => false,
    },
  });
  stop = () => {
    live = false;
    unsubscribe();
  };
  await restored;
}

/**
 * Health data kept outside the query cache, one key per item, under this prefix (the emergency
 * card's offline copy). Every such key is dropped with the cache.
 */
export const SNAPSHOT_PREFIX = "snapshot.";

let drops = 0;
/** Changes on every drop: a snapshot fetched before it must not be written after it. */
export function healthDropCount(): number {
  return drops;
}

/**
 * Health data may no longer be kept (a required consent withdrawn): every persisted query and
 * every snapshot query (`meta.snapshot`) leaves memory. The saved cache and every snapshot
 * leave the encrypted store now, not at the next save. The store is opened if it is not open
 * yet, so a drop never leaves health data on disk.
 */
export async function dropPersistedHealthData(): Promise<void> {
  drops += 1;
  queryClient.removeQueries({
    predicate: (query) => query.meta?.persist === true || query.meta?.snapshot === true,
  });
  const store = openLocalStore() ?? (await localStore().catch(() => null));
  store?.remove(CACHE_KEY);
  for (const key of store?.getAllKeys() ?? []) {
    if (key.startsWith(SNAPSHOT_PREFIX)) store?.remove(key);
  }
}

/** Before a wipe: stop writing the cache (the wipe then clears the store). */
export function stopCachePersistence(): void {
  generation += 1;
  stop?.();
  stop = null;
}
