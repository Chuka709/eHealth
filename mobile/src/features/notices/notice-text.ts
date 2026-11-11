import type { Notice } from "./use-notifications";

/** Kinds with a text of their own; anything newer from the server reads "a new notification". */
const KNOWN = new Set([
  "share_invite",
  "dose_overdue",
  "admin_reset",
  "admin_action",
  "review_ready",
  "critical_pending",
]);

export function noticeKey(notice: Pick<Notice, "kind">): string {
  return KNOWN.has(notice.kind) ? `kind.${notice.kind}` : "kind.other";
}

/** Notices with a screen of their own (the others are read in the list). */
export function hasDetail(notice: Pick<Notice, "kind" | "patient_id" | "entity_id">): boolean {
  return notice.kind === "dose_overdue" && notice.patient_id !== null && notice.entity_id !== null;
}
