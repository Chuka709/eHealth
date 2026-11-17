import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import type { LabReport } from "@/features/upload/use-reports";
import { api } from "@/lib/api";

/**
 * The person's review of a draft lab report (Phase 5.3-5.4). Every change goes to the server,
 * which recomputes the row (rule 6) and answers with the whole report: the app shows only
 * what the server computed - never a flag or a conversion of its own.
 */

export type ResultPatch = {
  raw_value?: string;
  raw_unit?: string;
  ref_text?: string;
  critical_text?: string;
  test_code?: string;
  acknowledge?: string[];
  clear?: ("raw_unit" | "ref_text" | "critical_text")[];
  /** accepting `implausible`: the value typed again from the printed report (Q57) */
  retyped_value?: string;
};
export type ResultNew = {
  raw_name: string;
  raw_value: string;
  raw_unit?: string;
  ref_text?: string;
  critical_text?: string;
  test_code?: string;
};
export type ReportPatch = {
  lab_name?: string;
  collected_at?: string;
  collected_precision?: "day" | "minute";
  acknowledge?: string[];
};
export type ManualReport = {
  document_id?: string;
  lab_name?: string;
  collected_at: string;
  collected_precision: "day" | "minute";
  results: ResultNew[];
};

const reportKey = (patientId: string | undefined, reportId: string) =>
  ["reports", patientId, reportId] as const;

async function fetchReport(patientId: string, reportId: string): Promise<LabReport> {
  const { data, error } = await api.GET("/api/v1/patients/{patient_id}/reports/{report_id}", {
    params: { path: { patient_id: patientId, report_id: reportId } },
  });
  if (error || !data) throw error ?? new Error("report");
  return data;
}

/** One report by its own id (a typed-in one has no document). */
export function useReport(patientId: string | undefined, reportId: string, enabled = true) {
  return useQuery({
    queryKey: reportKey(patientId, reportId),
    queryFn: () => fetchReport(patientId as string, reportId),
    enabled: patientId !== undefined && enabled,
    retry: false,
  });
}

/** Reports typed in without a file (a document's reports are opened from the document). */
export function useTypedReports(patientId: string | undefined) {
  return useQuery({
    queryKey: ["reports", patientId, "typed"],
    queryFn: async () => {
      const { data, error } = await api.GET("/api/v1/patients/{patient_id}/reports", {
        params: { path: { patient_id: patientId as string } },
      });
      if (error || !data) throw error ?? new Error("reports");
      return data;
    },
    enabled: patientId !== undefined,
  });
}

/** The catalog's tests, to pick the one a printed name means. */
export function useLabTests() {
  return useQuery({
    queryKey: ["lab-tests"],
    queryFn: async () => {
      const { data, error } = await api.GET("/api/v1/lab-tests");
      if (error || !data) throw error ?? new Error("lab-tests");
      return data;
    },
    staleTime: 60 * 60 * 1000,
  });
}

/** Keep every cached copy of the report as the server now has it. */
function useStore(patientId: string | undefined) {
  const client = useQueryClient();
  return (report: LabReport) => {
    client.setQueryData(reportKey(patientId, report.id), report);
    void client.invalidateQueries({ queryKey: ["reports", patientId, "typed"] });
    if (report.document_id) {
      client.setQueryData<LabReport[]>(
        ["documents", patientId, report.document_id, "reports"],
        (old) => old?.map((r) => (r.id === report.id ? report : r)),
      );
      void client.invalidateQueries({ queryKey: ["documents", patientId] });
    }
  };
}

function unwrap<T>({ data, error }: { data?: T; error?: unknown }): T {
  if (error !== undefined || data === undefined) throw error ?? new Error("review");
  return data;
}

export function useReviewActions(patientId: string | undefined, reportId: string) {
  const store = useStore(patientId);
  const path = { patient_id: patientId as string, report_id: reportId };
  const editResult = useMutation({
    mutationFn: async ({ resultId, patch }: { resultId: string; patch: ResultPatch }) =>
      unwrap(
        await api.PATCH("/api/v1/patients/{patient_id}/reports/{report_id}/results/{result_id}", {
          params: { path: { ...path, result_id: resultId } },
          body: patch,
        }),
      ),
    onSuccess: store,
  });
  const addResult = useMutation({
    mutationFn: async (row: ResultNew) =>
      unwrap(
        await api.POST("/api/v1/patients/{patient_id}/reports/{report_id}/results", {
          params: { path },
          body: row,
        }),
      ),
    onSuccess: store,
  });
  const deleteResult = useMutation({
    mutationFn: async ({ resultId, criticalSeen }: { resultId: string; criticalSeen: boolean }) => {
      const { error } = await api.DELETE(
        "/api/v1/patients/{patient_id}/reports/{report_id}/results/{result_id}",
        {
          params: {
            path: { ...path, result_id: resultId },
            query: { critical_seen: criticalSeen },
          },
        },
      );
      if (error) throw error;
      return fetchReport(patientId as string, reportId);
    },
    onSuccess: store,
  });
  const editReport = useMutation({
    mutationFn: async (patch: ReportPatch) =>
      unwrap(
        await api.PATCH("/api/v1/patients/{patient_id}/reports/{report_id}", {
          params: { path },
          body: patch,
        }),
      ),
    onSuccess: store,
  });
  const confirm = useMutation({
    mutationFn: async () =>
      unwrap(
        await api.POST("/api/v1/patients/{patient_id}/reports/{report_id}/confirm", {
          params: { path },
        }),
      ),
    onSuccess: store,
  });
  const reject = useMutation({
    mutationFn: async (criticalSeen: boolean) =>
      unwrap(
        await api.POST("/api/v1/patients/{patient_id}/reports/{report_id}/reject", {
          params: { path },
          body: { critical_seen: criticalSeen },
        }),
      ),
    onSuccess: store,
  });
  return { editResult, addResult, deleteResult, editReport, confirm, reject };
}

export function useCreateReport(patientId: string | undefined) {
  const store = useStore(patientId);
  return useMutation({
    mutationFn: async (body: ManualReport) =>
      unwrap(
        await api.POST("/api/v1/patients/{patient_id}/reports", {
          params: { path: { patient_id: patientId as string } },
          body,
        }),
      ),
    onSuccess: store,
  });
}

export function useMoveDocument(patientId: string | undefined, documentId: string) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: async (target: string) => {
      const { error } = await api.POST(
        "/api/v1/patients/{patient_id}/documents/{document_id}/move",
        {
          params: { path: { patient_id: patientId as string, document_id: documentId } },
          body: { patient_id: target },
        },
      );
      if (error) throw error;
    },
    onSuccess: () => void client.invalidateQueries({ queryKey: ["documents"] }),
  });
}
