import type { Notice } from "./use-notifications";

/** Kinds with a text of their own; anything newer from the server reads "a new notification". */
const KNOWN = new Set([
  "share_invite",
  "dose_overdue",
  "admin_reset",
  "admin_action",
  "review_ready",
  "critical_pending",
  "share_link_locked",
]);

export function noticeKey(notice: Pick<Notice, "kind" | "title_key">): string {
  // a doctor's or a viewer's invitation (7.1) shares the kind with a caregiver's
  if (notice.kind === "share_invite" && notice.title_key === "notification.share_invite") {
    return "kind.access_invite";
  }
  return KNOWN.has(notice.kind) ? `kind.${notice.kind}` : "kind.other";
}

/** Notices with a screen of their own (the others are read in the list). */
export function hasDetail(notice: Pick<Notice, "kind" | "patient_id" | "entity_id">): boolean {
  return (
    (notice.kind === "dose_overdue" || isResultNotice(notice)) &&
    notice.patient_id !== null &&
    notice.entity_id !== null
  );
}

/** A result to review (a read document, or a typed-in report that may be critical - 5.2/5.4). */
export function isResultNotice(notice: Pick<Notice, "kind">): boolean {
  return notice.kind === "review_ready" || notice.kind === "critical_pending";
}
