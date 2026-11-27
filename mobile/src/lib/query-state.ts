/** Offline with nothing kept a query waits ("paused") with no error: never a spinner then. */
export function loading(q: { isPending: boolean; fetchStatus: string }): boolean {
  return q.isPending && q.fetchStatus !== "paused";
}

/** What a screen shows for a query paused offline (it has no error of its own). */
export const OFFLINE_ERROR = new TypeError("Network request failed");
