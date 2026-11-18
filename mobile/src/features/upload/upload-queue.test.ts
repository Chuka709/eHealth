import { wipeLocalStore } from "@/lib/local-store";
import { queryClient } from "@/lib/query-client";

import { currentEpoch, wipeLocal } from "../auth/session";
import { setStatus } from "../auth/session-store";
import {
  dismissFailedUpload,
  enqueueUpload,
  failedUploads,
  flushUploads,
  MAX_PENDING_UPLOADS,
  pendingUploads,
  type SendUpload,
  tidyUploadFolder,
} from "./upload-queue";

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

// a tiny file system: uri -> exists; folders by prefix
const mockFiles = new Set<string>();
jest.mock("expo-file-system", () => {
  class Directory {
    uri: string;
    constructor(base: { uri?: string } | string, name?: string) {
      const root = typeof base === "string" ? base : (base.uri ?? "file:///data/user/0/pkg/files");
      this.uri = name ? `${root}/${name}` : root;
    }
    get exists() {
      return [...mockFiles].some((f) => f.startsWith(`${this.uri}/`)) || mockFiles.has(this.uri);
    }
    create() {
      mockFiles.add(this.uri);
    }
    list() {
      return [...mockFiles]
        .filter((f) => f.startsWith(`${this.uri}/`) && !f.slice(this.uri.length + 1).includes("/"))
        .map((f) => new MockFile(f));
    }
    delete() {
      for (const f of [...mockFiles])
        if (f === this.uri || f.startsWith(`${this.uri}/`)) mockFiles.delete(f);
    }
  }
  class MockFile {
    uri: string;
    constructor(base: { uri: string } | string, name?: string) {
      this.uri = typeof base === "string" ? base : `${base.uri}/${name}`;
    }
    get exists() {
      return mockFiles.has(this.uri);
    }
    delete() {
      mockFiles.delete(this.uri);
    }
    async copy(target: MockFile) {
      await new Promise((done) => setTimeout(done, 5)); // asynchronous, as in SDK 58
      if (!mockFiles.has(this.uri)) throw new Error("no source");
      mockFiles.add(target.uri);
    }
  }
  return {
    Directory,
    File: MockFile,
    Paths: {
      document: { uri: "file:///data/user/0/pkg/files" },
      cache: { uri: "file:///data/user/0/pkg/cache" },
    },
  };
});

const P = "00000000-0000-4000-8000-0000000000aa";
const id = (n: number) => `00000000-0000-4000-8000-${String(n).padStart(12, "0")}`;
const answer = (status: number, body: unknown = {}) =>
  new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });

async function queue(n: number) {
  const source = `file:///data/user/0/pkg/cache/scan-${n}.jpg`;
  mockFiles.add(source);
  return enqueueUpload({ uri: source, mime: "image/jpeg" }, P, id(n), currentEpoch());
}

beforeEach(async () => {
  await wipeLocalStore();
  mockStore.clear();
  mockFiles.clear();
  queryClient.clear();
  mockStore.set("lt.account", "11111111-1111-4111-8111-111111111111");
  setStatus("signedIn");
});

afterEach(() => queryClient.clear());

test("a picked file is copied into the app's own folder, then sent and removed", async () => {
  expect(await queue(1)).toBe("queued");
  const [waiting] = await pendingUploads();
  expect(waiting.uri).toBe(`file:///data/user/0/pkg/cache/upload-queue/${id(1)}.jpg`);
  expect(mockFiles.has(waiting.uri)).toBe(true);
  const send = jest.fn<ReturnType<SendUpload>, Parameters<SendUpload>>(async () => answer(201));
  expect(await flushUploads(send)).toBe(1);
  expect(send).toHaveBeenCalledWith(expect.objectContaining({ id: id(1), patientId: P }));
  expect(await pendingUploads()).toEqual([]);
  expect(mockFiles.has(waiting.uri)).toBe(false); // nothing of it left on the phone
});

test("tidying while a file is being added never removes the new copy (8.5)", async () => {
  // the app comes back from the picker: a send (with its tidy) starts as the file is added
  const source = "file:///data/user/0/pkg/cache/scan-9.jpg";
  mockFiles.add(source);
  const tidying = tidyUploadFolder(); // reads the list before the new file is in it
  const adding = enqueueUpload({ uri: source, mime: "image/jpeg" }, P, id(9), currentEpoch());
  await Promise.all([tidying, adding]);
  await tidyUploadFolder(); // and a later one too
  const [waiting] = await pendingUploads();
  expect(mockFiles.has(waiting.uri)).toBe(true);
});

test("the copy is whole before the picker's own file is removed (8.5)", async () => {
  // queueFiles removes the picker's copy as soon as the file is queued
  const source = "file:///data/user/0/pkg/cache/DocumentPicker/x.pdf";
  mockFiles.add(source);
  await enqueueUpload({ uri: source, mime: "application/pdf" }, P, id(8), currentEpoch());
  mockFiles.delete(source);
  const [waiting] = await pendingUploads();
  expect(mockFiles.has(waiting.uri)).toBe(true);
});

test("a file sent while another is being copied is not queued again (8.5 review M1)", async () => {
  await queue(1);
  const source = "file:///data/user/0/pkg/cache/scan-2.jpg";
  mockFiles.add(source);
  const adding = enqueueUpload({ uri: source, mime: "image/jpeg" }, P, id(2), currentEpoch());
  // the app came back from the picker: a send runs while the second file is copied
  const sent = await flushUploads(async () => answer(201));
  await adding;
  expect(sent).toBe(1);
  expect((await pendingUploads()).map((u) => u.id)).toEqual([id(2)]);
});

test("offline or a server error keeps the file for later, in order", async () => {
  await queue(1);
  await queue(2);
  expect(await flushUploads(async () => Promise.reject(new TypeError("offline")))).toBe(0);
  expect(await flushUploads(async () => answer(503))).toBe(0);
  expect((await pendingUploads()).map((u) => u.id)).toEqual([id(1), id(2)]);
  const order: string[] = [];
  await flushUploads(async (u) => {
    order.push(u.id);
    return answer(201);
  });
  expect(order).toEqual([id(1), id(2)]);
});

test("a file the server refuses is kept with its reason, never dropped silently", async () => {
  await queue(1);
  await flushUploads(async () => answer(415, { code: "document.unsupported_type" }));
  expect(await pendingUploads()).toEqual([]);
  const [failed] = await failedUploads();
  expect(failed).toEqual(
    expect.objectContaining({ id: id(1), status: 415, code: "document.unsupported_type" }),
  );
  expect(failed).not.toHaveProperty("uri");
  await dismissFailedUpload(id(1));
  expect(await failedUploads()).toEqual([]);
});

test("the queue has a limit", async () => {
  for (let n = 0; n < MAX_PENDING_UPLOADS; n += 1) expect(await queue(n)).toBe("queued");
  expect(await queue(999)).toBe("full");
});

test("signing out removes waiting files and the list", async () => {
  await queue(1);
  const [waiting] = await pendingUploads();
  await wipeLocal("signedOut");
  expect(mockFiles.has(waiting.uri)).toBe(false);
  mockStore.set("lt.account", "11111111-1111-4111-8111-111111111111");
  setStatus("signedIn");
  expect(await pendingUploads()).toEqual([]);
});

test("a waiting file the system removed is reported, and the next ones still go", async () => {
  await queue(1);
  await queue(2);
  const [first] = await pendingUploads();
  mockFiles.delete(first.uri); // the cache was cleared under storage pressure
  const send = jest.fn<ReturnType<SendUpload>, Parameters<SendUpload>>(async () => answer(201));
  expect(await flushUploads(send)).toBe(1);
  expect(send).toHaveBeenCalledTimes(1);
  expect((await failedUploads()).map((f) => [f.id, f.code])).toEqual([[id(1), "file_missing"]]);
});

test("the picker's own copy in the cache is removed once ours exists", async () => {
  const { removeSourceCopy } =
    jest.requireActual<typeof import("./upload-files")>("./upload-files");
  mockFiles.add("file:///data/user/0/pkg/cache/ImagePicker/a.jpg");
  mockFiles.add("file:///elsewhere/b.pdf");
  removeSourceCopy("file:///data/user/0/pkg/cache/ImagePicker/a.jpg");
  removeSourceCopy("file:///elsewhere/b.pdf");
  expect(mockFiles.has("file:///data/user/0/pkg/cache/ImagePicker/a.jpg")).toBe(false);
  expect(mockFiles.has("file:///elsewhere/b.pdf")).toBe(true); // another app's file is untouched
});

test("a shared path inside this app's private data is refused (commit security review 3.5)", () => {
  const { isForeignFile } = jest.requireActual<typeof import("./upload-files")>("./upload-files");
  expect(isForeignFile("content://com.android.providers.media.documents/document/1")).toBe(true);
  expect(isForeignFile("file:///storage/emulated/0/Download/x.pdf")).toBe(true);
  expect(isForeignFile("file:///data/user/0/pkg/cache/share-copy/x.pdf")).toBe(true);
  expect(isForeignFile("file:///data/user/0/pkg/files/mmkv/lt.local")).toBe(false);
  expect(isForeignFile("file:///data/user/0/pkg/cache/upload-queue/other.pdf")).toBe(false);
  expect(isForeignFile("file:///data/data/pkg/files/mmkv/lt.local")).toBe(false); // an alias
  expect(isForeignFile("file:///storage/../data/user/0/pkg/files/x")).toBe(false);
});
