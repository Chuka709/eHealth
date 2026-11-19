import { useMutation } from "@tanstack/react-query";

import {
  type ShareResult,
  shareFile,
  startExport,
  writeForSharing,
} from "@/features/emergency/export-files";
import { api } from "@/lib/api";
import { apiError } from "@/lib/use-error-text";

/**
 * The doctor's summary PDF (anyone who reads the profile) and the owner's data export (JSON or
 * FHIR), Phase 7.6 over the 7.5 API. The server makes the file; the phone writes it once into
 * the export folder under a fixed name (no name or id of the person) and hands it to the share
 * sheet, the only way it leaves the app (rule 8). Never cached, never in the gallery.
 */

export type ExportKind = "summary" | "json" | "fhir";

const FILES = {
  summary: { name: "labtrack-summary.pdf", mime: "application/pdf" },
  json: { name: "labtrack-export.json", mime: "application/json" },
  fhir: { name: "labtrack-export-fhir.json", mime: "application/json" },
} as const;

async function fetchBytes(
  kind: ExportKind,
  patientId: string,
  months: number,
  lang: "mn" | "en",
): Promise<ArrayBuffer> {
  const path = { patient_id: patientId };
  const { data, error } =
    kind === "summary"
      ? await api.GET("/api/v1/patients/{patient_id}/summary.pdf", {
          params: { path, query: { months, lang } },
          parseAs: "arrayBuffer",
        })
      : kind === "json"
        ? await api.GET("/api/v1/patients/{patient_id}/export.json", {
            params: { path },
            parseAs: "arrayBuffer",
          })
        : await api.GET("/api/v1/patients/{patient_id}/export.fhir.json", {
            params: { path },
            parseAs: "arrayBuffer",
          });
  if (!data) throw apiError(error);
  return data;
}

export function useExportFile(patientId: string) {
  return useMutation({
    gcTime: 0,
    mutationFn: async (input: {
      kind: ExportKind;
      months: number;
      lang: "mn" | "en";
    }): Promise<ShareResult> => {
      // taken first: a sign-out while the file downloads drops it
      const ticket = startExport();
      const bytes = await fetchBytes(input.kind, patientId, input.months, input.lang);
      const { name, mime } = FILES[input.kind];
      const file = await writeForSharing(ticket, new Uint8Array(bytes), name);
      return shareFile(ticket, file, mime);
    },
  });
}
