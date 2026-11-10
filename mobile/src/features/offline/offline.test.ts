import { onlineManager } from "@tanstack/react-query";
import { createMMKV } from "react-native-mmkv";
import { setWizardActive, wizardActive } from "@/features/records/onboarding-store";
import { localStore, openLocalStore, wipeLocalStore } from "@/lib/local-store";
import {
  dropPersistedHealthData,
  startCachePersistence,
  stopCachePersistence,
} from "@/lib/persist";
import { queryClient } from "@/lib/query-client";

import { currentEpoch, establishSession, refreshSession, wipeLocal } from "../auth/session";
import { setStatus, tokenSubject } from "../auth/session-store";
import { dismissFailed, enqueue, failedWrites, flush, pendingWrites, type Send } from "./queue";

const mockStore = new Map<string, string>();
jest.mock("expo-secure-store", () => ({
  WHEN_UNLOCKED_THIS_DEVICE_ONLY: 6,
  getItemAsync: jest.fn(async (key: string) => mockStore.get(key) ?? null),
  setItemAsync: jest.fn(async (key: string, value: string) => {
    mockStore.set(key, value);
  }),
  deleteItemAsync: jest.fn(async (key: string) => {
    mockStore.delete(key);
  }),
}));

const notifications = jest.requireMock<{
  cancelAllScheduledNotificationsAsync: jest.Mock;
  dismissAllNotificationsAsync: jest.Mock;
}>("expo-notifications");

const write = (n: number) => ({
  id: `00000000-0000-4000-8000-${String(n).padStart(12, "0")}`,
  method: "POST" as const,
  path: "/api/v1/patients/p/intakes",
  body: { client_id: `c${n}`, status: "taken" },
});

const answer = (status: number, body: unknown = {}) =>
  new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });

const ALICE = "11111111-1111-4111-8111-111111111111";
const BOB = "22222222-2222-4222-8222-222222222222";

function signedInAs(account: string) {
  mockStore.set("lt.account", account);
  setStatus("signedIn");
}

/** An access token as the API issues it, with `sub` = account (unsigned: only read here). */
function tokenFor(account: string) {
  const b64 = (o: object) => Buffer.from(JSON.stringify(o)).toString("base64url");
  return `${b64({ alg: "ES256" })}.${b64({ sub: account })}.sig`;
}

// Cached queries keep a 5-minute garbage-collection timer: clear them so Jest can exit.
afterEach(() => {
  stopCachePersistence();
  queryClient.clear();
  onlineManager.setOnline(true);
});

beforeEach(async () => {
  stopCachePersistence();
  await wipeLocalStore();
  mockStore.clear();
  queryClient.clear();
  jest.clearAllMocks();
  signedInAs(ALICE);
});

describe("encrypted local store", () => {
  it("keeps its id and AES-256 key in the secure store, one store per key", async () => {
    const first = await localStore();
    expect(await localStore()).toBe(first);
    const keyring = JSON.parse(mockStore.get("lt.local_store") ?? "{}");
    expect(keyring.key).toHaveLength(32);
    expect(keyring.id).toMatch(/^lt\.local\./);
    first.set("x", "1");

    await wipeLocalStore();
    expect(mockStore.has("lt.local_store")).toBe(false); // the key is gone: crypto-shredded
    expect(openLocalStore()).toBeNull();
    const next = await localStore();
    expect(JSON.parse(mockStore.get("lt.local_store") ?? "{}").id).not.toBe(keyring.id);
    expect(next.getString("x")).toBeUndefined();
  });

  it("starts a fresh store when the saved keyring is unreadable", async () => {
    mockStore.set("lt.local_store", "{not json");
    const store = await localStore();
    expect(store.getAllKeys()).toEqual([]);
    expect(JSON.parse(mockStore.get("lt.local_store") ?? "{}").key).toHaveLength(32);
  });
});

describe("offline queue", () => {
  it("sends in order and removes what the server stored", async () => {
    for (const n of [1, 2, 3]) await enqueue(write(n));
    await enqueue(write(2)); // the same record queued twice stays once
    const seen: string[] = [];
    const send: Send = async (w) => {
      seen.push(w.id);
      return answer(201);
    };
    expect(await flush(send)).toBe(3);
    expect(seen).toEqual([write(1).id, write(2).id, write(3).id]);
    expect(await pendingWrites()).toEqual([]);
  });

  it("keeps everything when offline, on 5xx, 429 or 401 - and stops there", async () => {
    for (const failure of [
      async () => {
        throw new TypeError("Network request failed");
      },
      async () => answer(503),
      async () => answer(429),
      async () => answer(401),
    ] satisfies Send[]) {
      await enqueue(write(1));
      await enqueue(write(2));
      const send = jest.fn(failure);
      expect(await flush(send)).toBe(0);
      expect(send).toHaveBeenCalledTimes(1); // order kept: nothing jumps the stuck one
      expect((await pendingWrites()).map((w) => w.id)).toEqual([write(1).id, write(2).id]);
      await wipeLocalStore();
    }
  });

  it("never drops a refused write silently", async () => {
    await enqueue(write(1));
    await enqueue(write(2));
    const send: Send = async (w) =>
      w.id === write(1).id ? answer(422, { code: "validation" }) : answer(201);
    expect(await flush(send)).toBe(1);
    const failed = await failedWrites();
    expect(failed.map((f) => [f.id, f.status, f.code])).toEqual([[write(1).id, 422, "validation"]]);
    expect(await pendingWrites()).toEqual([]);
    await dismissFailed(write(1).id);
    expect(await failedWrites()).toEqual([]);
  });

  it("is single-flight and refuses more than it can hold", async () => {
    await enqueue(write(1));
    let release: (r: Response) => void = () => undefined;
    const send = jest.fn(() => new Promise<Response>((resolve) => (release = resolve)));
    const a = flush(send);
    const b = flush(send);
    await Promise.resolve();
    release(answer(201));
    expect(await a).toBe(1);
    expect(await b).toBe(1);
    expect(send).toHaveBeenCalledTimes(1);

    for (let n = 0; n < 500; n += 1) expect(await enqueue(write(1000 + n))).toBe(true);
    expect(await enqueue(write(9999))).toBe(false);
  });

  it("does not write a sent item back after a sign-out wiped the queue", async () => {
    await enqueue(write(1));
    let release: (r: Response) => void = () => undefined;
    const done = flush(() => new Promise<Response>((resolve) => (release = resolve)));
    await Promise.resolve();
    await wipeLocalStore();
    release(answer(201));
    await done;
    expect(await pendingWrites()).toEqual([]);
    expect(await failedWrites()).toEqual([]);
  });
});

describe("persisted query cache", () => {
  it("saves only queries that opt in", async () => {
    await startCachePersistence();
    queryClient.setQueryData(["meds"], [{ id: "m1" }]);
    queryClient
      .getQueryCache()
      .find({ queryKey: ["meds"] })
      ?.setOptions({
        queryKey: ["meds"],
        meta: { persist: true },
      });
    queryClient.setQueryData(["sessions"], [{ id: "s1" }]);
    queryClient.setQueryData(["meds"], [{ id: "m1" }, { id: "m2" }]); // a change after opt-in
    await new Promise((resolve) => setTimeout(resolve, 1300)); // the persister's throttle
    const saved = (await localStore()).getString("query-cache") ?? "";
    expect(saved).toContain("m2");
    expect(saved).not.toContain("s1");
  });
});

describe("sign-out", () => {
  it("clears the local store, its key and every local notification", async () => {
    await enqueue(write(1));
    await wipeLocal("signedOut");
    expect(mockStore.has("lt.local_store")).toBe(false);
    expect(notifications.cancelAllScheduledNotificationsAsync).toHaveBeenCalled();
    expect(notifications.dismissAllNotificationsAsync).toHaveBeenCalled();
    signedInAs(ALICE);
    expect(await pendingWrites()).toEqual([]); // the same account again: a new, empty store
  });
});

describe("one account's data never reaches another", () => {
  it("refuses to open the store when nobody is signed in", async () => {
    setStatus("signedOut");
    await expect(localStore()).rejects.toThrow("not signed in");
    await expect(enqueue(write(1))).rejects.toThrow();
  });

  it("discards a store left by another account whose wipe did not finish", async () => {
    await localStore();
    const alice = JSON.parse(mockStore.get("lt.local_store") ?? "{}");
    // A cold start, then a sign-out whose wipe never ran: Alice's keyring and data are still
    // on the phone, and this process never opened her store.
    await wipeLocalStore();
    mockStore.set("lt.local_store", JSON.stringify(alice));
    const leftover = createMMKV({ id: alice.id, encryptionKey: alice.key });
    leftover.set("queue.pending.v1", JSON.stringify([write(1)]));
    leftover.set("query-cache", "alice's cache");
    signedInAs(BOB);
    expect(await pendingWrites()).toEqual([]);
    expect((await localStore()).getString("query-cache")).toBeUndefined();
    expect(JSON.parse(mockStore.get("lt.local_store") ?? "{}").account).toBe(BOB);
    expect(leftover.getAllKeys()).toEqual([]); // Alice's store emptied, never opened for Bob
  });

  it("stops a flush when the session changes and never replays it on the new one", async () => {
    await enqueue(write(1));
    await enqueue(write(2));
    let release: (r: Response) => void = () => undefined;
    const send = jest.fn(() => new Promise<Response>((resolve) => (release = resolve)));
    const done = flush(send);
    await Promise.resolve();
    const before = currentEpoch();
    await establishSession({
      access_token: tokenFor(BOB),
      refresh_token: "r",
      expires_in: 900,
      token_type: "bearer",
    } as Parameters<typeof establishSession>[0]);
    expect(currentEpoch()).not.toBe(before);
    release(answer(201));
    await done;
    expect(send).toHaveBeenCalledTimes(1); // the second write was not sent under Bob
  });

  it("records the account of a new sign-in from its token", async () => {
    await establishSession({
      access_token: tokenFor(BOB),
      refresh_token: "r",
      expires_in: 900,
      token_type: "bearer",
    } as Parameters<typeof establishSession>[0]);
    expect(mockStore.get("lt.account")).toBe(BOB);
  });
});

describe("persistence edge cases", () => {
  it("never writes a mutation (a paused one holds its variables)", async () => {
    await startCachePersistence();
    // offline: the mutation pauses, holding its variables
    onlineManager.setOnline(false);
    const mutation = queryClient.getMutationCache().build(queryClient, {
      mutationFn: async (_: { new_password: string }) => undefined,
    });
    void mutation.execute({ new_password: "hunter22" }).catch(() => undefined);
    await Promise.resolve();
    expect(mutation.state.isPaused).toBe(true);
    queryClient.setQueryData(["meds"], [{ id: "m3" }]);
    queryClient
      .getQueryCache()
      .find({ queryKey: ["meds"] })
      ?.setOptions({
        queryKey: ["meds"],
        meta: { persist: true },
      });
    queryClient.setQueryData(["meds"], [{ id: "m4" }]);
    await new Promise((resolve) => setTimeout(resolve, 1300));
    const saved = (await localStore()).getString("query-cache") ?? "";
    expect(saved).toContain("m4");
    expect(saved).not.toContain("hunter22");
    queryClient.getMutationCache().clear(); // leave no paused mutation waiting for the network
    onlineManager.setOnline(true);
  });

  it("starts once when asked twice, and a stop silences it", async () => {
    await Promise.all([startCachePersistence(), startCachePersistence()]);
    stopCachePersistence();
    queryClient.setQueryData(["meds"], [{ id: "late" }]);
    queryClient
      .getQueryCache()
      .find({ queryKey: ["meds"] })
      ?.setOptions({
        queryKey: ["meds"],
        meta: { persist: true },
      });
    queryClient.setQueryData(["meds"], [{ id: "later" }]);
    await new Promise((resolve) => setTimeout(resolve, 1300));
    expect((await localStore()).getString("query-cache") ?? "").not.toContain("later");
  });
});

describe("a sign-out in progress", () => {
  it("sends no queued write and lets no refresh write a token back", async () => {
    await enqueue(write(1));
    mockStore.set("lt.refresh", "old-refresh");
    const send = jest.fn(async () => answer(201));
    const wipe = wipeLocal("signedOut");
    const flushed = flush(send); // a reconnect fires mid-wipe
    expect(await refreshSession()).toBe("signedOut");
    await wipe;
    await flushed;
    expect(send).not.toHaveBeenCalled();
    expect(mockStore.has("lt.refresh")).toBe(false);
  });

  it("reads an access token's account whatever its padding", () => {
    for (const account of [ALICE, BOB]) expect(tokenSubject(tokenFor(account))).toBe(account);
    expect(tokenSubject("not.a-token")).toBeNull();
    expect(tokenSubject(null)).toBeNull();
  });
});

describe("when health data may no longer be kept", () => {
  it("a withdrawn consent drops persisted health data from memory and the store", async () => {
    await startCachePersistence();
    const store = await localStore();
    store.set("query-cache", "transplants of the user");
    queryClient.setQueryData(["transplants", "p1"], [{ id: "t1" }]);
    queryClient
      .getQueryCache()
      .find({ queryKey: ["transplants", "p1"] })
      ?.setOptions({
        queryKey: ["transplants", "p1"],
        meta: { persist: true },
      });
    queryClient.setQueryData(["me"], { id: "u1" }); // not health data: stays
    await dropPersistedHealthData();
    expect(queryClient.getQueryData(["transplants", "p1"])).toBeUndefined();
    expect(queryClient.getQueryData(["me"])).toEqual({ id: "u1" });
    // the running persister may save the now empty cache again: never the dropped data
    expect(store.getString("query-cache") ?? "").not.toContain("transplants");
  });

  it("a sign-out ends an unfinished onboarding wizard", async () => {
    setWizardActive(true);
    await wipeLocal("signedOut");
    expect(wizardActive()).toBe(false);
  });
});
