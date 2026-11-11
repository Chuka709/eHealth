/**
 * Where a tap on a server push leads (Phase 2.8f). The push carries only the notification's id
 * and kind (2.8b L3); everything else is read from the API once the app is open, so a push can
 * never make the app record or show anything by itself.
 */

export type PushData = { notificationId: number; kind: string };

/** The push's own data, or null for anything that is not one of ours. */
export function pushData(raw: unknown): PushData | null {
  if (typeof raw !== "object" || raw === null) return null;
  const { notification_id: id, kind } = raw as { notification_id?: unknown; kind?: unknown };
  if (typeof id !== "number" || !Number.isSafeInteger(id) || id < 1) return null;
  if (typeof kind !== "string" || !/^[a-z_]{1,40}$/.test(kind)) return null;
  return { notificationId: id, kind };
}

/** The screen to open: a notice with details of its own, or the list. */
export function pushRoute(data: PushData | null): string {
  if (data?.kind === "dose_overdue") return `/notifications/${data.notificationId}`;
  return "/notifications";
}
