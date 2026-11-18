import { currentEpoch, isWiping } from "@/features/auth/session";
import { getStatus } from "@/features/auth/session-store";
import { localStore } from "@/lib/local-store";

import { copyIn, fileExists, removeFile, removeStrays } from "./upload-files";

/**
 * Lab result files waiting to be sent (Phase 3.4; docs/08 "Хариу оруулах" 4): a scan in
 * airplane mode is kept and sent once online. The list lives in the encrypted local store,
 * the file in the app's private folder (upload-files.ts). Each file has its own `client_id`:
 * the server keeps one document per id, so a file sent twice (the app killed between "sent" and
 * "removed") is still one document. Outcomes as the write queue (features/offline/queue.ts):
 *   2xx                      sent: removed with its file
 *   network, 5xx, 429, 401   kept, retried later
 *   other 4xx                refused (too large, not a PDF/picture, unsafe PDF): kept in
 *                            `failed` for the user to see, its file removed
 */

export type PendingUpload = {
  id: string; // client_id
  patientId: string;
  uri: string; // the private copy
  mime: string;
  createdAt: number;
};

export type FailedUpload = Omit<PendingUpload, "uri"> & { status: number; code: string | null };

const PENDING = "uploads.pending.v1";
const FAILED = "uploads.failed.v1";
export const MAX_PENDING_UPLOADS = 40;

export type SendUpload = (upload: PendingUpload) => Promise<Response>;

function read<T>(raw: string | undefined): T[] {
  if (!raw) return [];
  try {
    const parsed: unknown = JSON.parse(raw);
    return Array.isArray(parsed) ? (parsed as T[]) : [];
  } catch {
    return [];
  }
}

export async function pendingUploads(): Promise<PendingUpload[]> {
  return read<PendingUpload>((await localStore()).getString(PENDING));
}

export async function failedUploads(): Promise<FailedUpload[]> {
  return read<FailedUpload>((await localStore()).getString(FAILED));
}

const sessionIs = (epoch: number) =>
  currentEpoch() === epoch && !isWiping() && getStatus() === "signedIn";

/**
 * Queue a picked file for a profile: copied first, so the source (a scan in the cache, a file
 * from another app) may go away. "full" when too many wait (the user goes online first).
 */
/**
 * Adding a file and tidying the folder take turns (8.5, found on the emulator): the app coming
 * back from the picker or share sheet starts a send, whose tidy read the list before the new
 * file was in it and then deleted the new copy as a stray ("file_missing", nothing sent).
 */
let folderLock: Promise<unknown> = Promise.resolve();

function withFolderLock<T>(work: () => Promise<T>): Promise<T> {
  const next = folderLock.then(work, work);
  folderLock = next.catch(() => undefined);
  return next;
}

export function enqueueUpload(
  file: { uri: string; mime: string },
  patientId: string,
  id: string,
  epoch: number,
): Promise<"queued" | "full"> {
  return withFolderLock(() => addToQueue(file, patientId, id, epoch));
}

async function addToQueue(
  file: { uri: string; mime: string },
  patientId: string,
  id: string,
  epoch: number,
): Promise<"queued" | "full"> {
  const store = await localStore();
  if (!sessionIs(epoch)) throw new Error("session changed");
  if (read<PendingUpload>(store.getString(PENDING)).length >= MAX_PENDING_UPLOADS) return "full";
  const uri = await copyIn(file.uri, id, file.mime);
  if (!sessionIs(epoch)) {
    removeFile(uri);
    throw new Error("session changed");
  }
  // read again after the copy: a send running meanwhile may have removed entries (sent or
  // refused); writing the list read before would bring them back (security review 8.5 M1)
  const pending = read<PendingUpload>(store.getString(PENDING));
  if (pending.length >= MAX_PENDING_UPLOADS) {
    removeFile(uri);
    return "full";
  }
  pending.push({ id, patientId, uri, mime: file.mime, createdAt: Date.now() });
  store.set(PENDING, JSON.stringify(pending));
  return "queued";
}

export async function dismissFailedUpload(id: string): Promise<void> {
  const store = await localStore();
  const failed = read<FailedUpload>(store.getString(FAILED)).filter((f) => f.id !== id);
  store.set(FAILED, JSON.stringify(failed));
}

async function errorCode(response: Response): Promise<string | null> {
  const body: unknown = await response.json().catch(() => null);
  return typeof body === "object" &&
    body !== null &&
    "code" in body &&
    typeof body.code === "string"
    ? body.code
    : null;
}

const retryLater = (status: number) => status === 401 || status === 429 || status >= 500;

let running: { epoch: number; done: Promise<number> } | null = null;

/** Send waiting files, oldest first, one at a time; single-flight per session. */
export function flushUploads(send: SendUpload): Promise<number> {
  const epoch = currentEpoch();
  if (running?.epoch !== epoch) {
    const current = {
      epoch,
      done: run(send, epoch).finally(() => {
        if (running === current) running = null;
      }),
    };
    running = current;
  }
  return running.done;
}

async function run(send: SendUpload, epoch: number): Promise<number> {
  const store = await localStore();
  let sent = 0;
  for (;;) {
    if (!sessionIs(epoch)) return sent;
    const [next] = read<PendingUpload>(store.getString(PENDING));
    if (!next) return sent;
    if (!fileExists(next.uri)) {
      // the system cleared the cache before it was sent: said, never sent empty (review M1)
      move(store, next, 0, "file_missing");
      continue;
    }
    let response: Response;
    try {
      response = await send(next);
    } catch {
      return sent; // offline: try again later
    }
    if (!sessionIs(epoch)) return sent;
    if (!response.ok && retryLater(response.status)) return sent;
    if (!response.ok) {
      move(store, next, response.status, await errorCode(response));
    } else {
      sent += 1;
      drop(store, next);
    }
  }
}

type Store = Awaited<ReturnType<typeof localStore>>;

function drop(store: Store, upload: PendingUpload): void {
  const rest = read<PendingUpload>(store.getString(PENDING)).filter((p) => p.id !== upload.id);
  store.set(PENDING, JSON.stringify(rest));
  removeFile(upload.uri);
}

/** Refused (or its file gone): kept with why, without the file. */
function move(store: Store, upload: PendingUpload, status: number, code: string | null): void {
  const { uri: _uri, ...kept } = upload;
  const failed = read<FailedUpload>(store.getString(FAILED));
  failed.push({ ...kept, status, code });
  store.set(FAILED, JSON.stringify(failed));
  drop(store, upload);
}

/** Files nothing waits for any more are removed (review M2); run before each flush. */
export function tidyUploadFolder(): Promise<void> {
  return withFolderLock(async () => {
    const keep = new Set((await pendingUploads()).map((u) => u.uri));
    removeStrays(keep);
  });
}
