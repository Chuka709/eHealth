import { createAsyncStoragePersister } from "@tanstack/query-async-storage-persister";
import { persistQueryClient } from "@tanstack/react-query-persist-client";

import { localStore } from "./local-store";
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

/** Before a wipe: stop writing the cache (the wipe then clears the store). */
export function stopCachePersistence(): void {
  generation += 1;
  stop?.();
  stop = null;
}
