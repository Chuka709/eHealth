import { currentEpoch, isWiping } from "@/features/auth/session";
import { getStatus } from "@/features/auth/session-store";
import { localStore, openLocalStore } from "@/lib/local-store";

/**
 * Writes made without a network (a dose marked taken in airplane mode, a vital entered
 * offline) wait here, in the encrypted local store, and are sent in order once online.
 *
 * Every queued body carries the record's `client_id`: the server stores one row per client_id
 * (migration 0014), so sending an item twice - the app killed between "sent" and "removed" -
 * never duplicates it. Outcomes:
 *   2xx           sent: removed
 *   network, 5xx, 429, 401   not now: kept, the flush stops and is retried later (a 401 means
 *                 the session is being refreshed or has ended - a wipe then clears the queue)
 *   other 4xx     the server refused it (validation, conflict, no access): moved to `failed`,
 *                 kept for the user to see - a record is never dropped silently
 */

export type QueuedWrite = {
  id: string; // the body's client_id
  method: "POST";
  path: string; // e.g. /api/v1/patients/<id>/intakes
  body: Record<string, unknown>;
  createdAt: number;
};

export type FailedWrite = QueuedWrite & { status: number; code: string | null };

const PENDING = "queue.pending.v1";
const FAILED = "queue.failed.v1";
const MAX_PENDING = 500;

export type Send = (write: QueuedWrite) => Promise<Response>;

function read<T>(raw: string | undefined): T[] {
  if (!raw) return [];
  try {
    const parsed: unknown = JSON.parse(raw);
    return Array.isArray(parsed) ? (parsed as T[]) : [];
  } catch {
    return [];
  }
}

export async function pendingWrites(): Promise<QueuedWrite[]> {
  return read<QueuedWrite>((await localStore()).getString(PENDING));
}

export async function failedWrites(): Promise<FailedWrite[]> {
  return read<FailedWrite>((await localStore()).getString(FAILED));
}

/** Queue a write; false when the queue is full (the caller tells the user to go online). */
export async function enqueue(write: Omit<QueuedWrite, "createdAt">): Promise<boolean> {
  const store = await localStore();
  const pending = read<QueuedWrite>(store.getString(PENDING));
  if (pending.some((p) => p.id === write.id)) return true; // already queued
  if (pending.length >= MAX_PENDING) return false;
  pending.push({ ...write, createdAt: Date.now() });
  store.set(PENDING, JSON.stringify(pending));
  return true;
}

/** The user has seen a refused write: forget it. */
export async function dismissFailed(id: string): Promise<void> {
  const store = await localStore();
  const failed = read<FailedWrite>(store.getString(FAILED)).filter((f) => f.id !== id);
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

const sessionIs = (epoch: number) =>
  currentEpoch() === epoch && !isWiping() && getStatus() === "signedIn";

const retryLater = (status: number) => status === 401 || status === 429 || status >= 500;

let running: { epoch: number; done: Promise<number> } | null = null;

/**
 * Send what is queued, oldest first, one at a time (a dose and its correction stay in order).
 * Single-flight: a second call while one runs joins it. Returns how many were sent.
 */
export function flush(send: Send): Promise<number> {
  const epoch = currentEpoch();
  // a flush of an earlier session never stands in for this one's
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

async function run(send: Send, epoch: number): Promise<number> {
  const store = await localStore();
  let sent = 0;
  for (;;) {
    if (!sessionIs(epoch)) return sent; // signed out, wiping or in again: stop
    const [next] = read<QueuedWrite>(store.getString(PENDING));
    if (!next) return sent;
    let response: Response;
    try {
      response = await send(next);
    } catch {
      return sent; // offline: try again later
    }
    if (!sessionIs(epoch)) return sent;
    if (retryLater(response.status)) return sent;
    const code = response.ok ? null : await errorCode(response);
    if (!sessionIs(epoch) || openLocalStore() !== store) return sent;
    // The store may have been wiped meanwhile (sign-out): re-read before writing back.
    const pending = read<QueuedWrite>(store.getString(PENDING));
    if (pending[0]?.id !== next.id) return sent;
    store.set(PENDING, JSON.stringify(pending.slice(1)));
    if (response.ok) {
      sent += 1;
    } else {
      const failed = read<FailedWrite>(store.getString(FAILED));
      failed.push({ ...next, status: response.status, code });
      store.set(FAILED, JSON.stringify(failed));
    }
  }
}
