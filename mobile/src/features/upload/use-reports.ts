import { useQuery } from "@tanstack/react-query";

import { api } from "@/lib/api";

export type LabReport = Awaited<ReturnType<typeof documentReports>>[number];
export type LabResult = LabReport["results"][number];

async function documentReports(patientId: string, documentId: string) {
  const { data, error } = await api.GET(
    "/api/v1/patients/{patient_id}/documents/{document_id}/reports",
    { params: { path: { patient_id: patientId, document_id: documentId } } },
  );
  if (error || !data) throw error ?? new Error("reports");
  return data;
}

/** What was read from one document: drafts for the profile's writers (rule 4: not confirmed). */
export function useDocumentReports(patientId: string | undefined, documentId: string) {
  return useQuery({
    queryKey: ["documents", patientId, documentId, "reports"],
    queryFn: () => documentReports(patientId as string, documentId),
    enabled: patientId !== undefined,
  });
}

/** Why a document failed, as the app tells it (error codes from the worker, 3.2-4.5). */
export type FailReason = "not_read" | "temporary" | "unreadable" | "infected";

const TEMPORARY = new Set(["extraction_timeout", "extraction_error", "scan_unavailable"]);

export function failReason(code: string | null | undefined): FailReason {
  if (!code) return "temporary"; // failed without a reason: try again
  if (code === "infected") return "infected";
  if (code === "unreadable") return "unreadable";
  if (TEMPORARY.has(code)) return "temporary";
  // not_read, consent_withdrawn and every ai_* code: the file is kept, not read automatically
  return "not_read";
}

/** The issue codes a result row may carry (0031/0032), each with its own text; a code
 * this app does not know yet is still shown, as "other" (never dropped - medical review 4.6). */
export const ISSUE_CODES = [
  "not_in_source",
  "implausible",
  "ref_suspicious",
  "flag_mismatch",
  "unknown_unit",
  "unknown_test",
  "date_future",
  "date_old",
  "date_ambiguous",
  "name_mismatch",
  "possible_duplicate",
  "large_delta",
  "low_confidence",
  "name_missing",
  "date_missing",
  "date_inconsistent",
  "unit_missing",
  "truncated",
] as const;
export type IssueCode = (typeof ISSUE_CODES)[number] | "other";

export function knownIssues(issues: readonly string[]): IssueCode[] {
  const out = issues.map(
    (i): IssueCode => ((ISSUE_CODES as readonly string[]).includes(i) ? (i as IssueCode) : "other"),
  );
  return [...new Set(out)];
}
