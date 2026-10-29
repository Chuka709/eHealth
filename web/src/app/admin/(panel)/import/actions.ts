"use server";

import type { components } from "@labtrack/shared";

import { type ActionResult, adminApi, failure } from "@/lib/server/api";

// The CSV is itself sensitive (a patient list): it passes through in memory to the API and is
// never stored, logged or echoed back beyond what the preview shows (row, username, name,
// last 4 phone digits).

const MAX_BYTES = 1_000_000;

export type Preview = components["schemas"]["ImportPreviewOut"];
export type ImportOutcome =
  | { kind: "preview"; preview: Preview }
  | { kind: "done"; created: number }
  | { kind: "invalid"; problems: components["schemas"]["ImportProblemOut"][] };

async function csvBody(form: FormData): Promise<Uint8Array | null> {
  const file = form.get("file");
  if (!(file instanceof File) || file.size === 0 || file.size > MAX_BYTES) return null;
  return new Uint8Array(await file.arrayBuffer());
}

function raw(bytes: Uint8Array) {
  // The file's exact bytes: the API checks the encoding itself and hashes these bytes (the
  // preview's sha256 must match the commit). openapi-fetch would JSON-encode a string body.
  return { body: "", bodySerializer: () => bytes, headers: { "Content-Type": "text/csv" } };
}

export async function importCsv(
  _: ActionResult<ImportOutcome> | null,
  form: FormData,
): Promise<ActionResult<ImportOutcome>> {
  const csv = await csvBody(form);
  if (csv === null) return { ok: false, code: "admin.import_too_large" };
  const api = await adminApi();
  const sha256 = form.get("sha256");
  if (typeof sha256 !== "string" || !/^[0-9a-f]{64}$/.test(sha256)) {
    const { data, error, response } = await api.POST(
      "/api/v1/admin/users/import/preview",
      raw(csv),
    );
    return data
      ? { ok: true, data: { kind: "preview", preview: data } }
      : failure(error, response.status);
  }
  const { data, error, response } = await api.POST("/api/v1/admin/users/import", {
    ...raw(csv),
    params: { query: { sha256 } },
  });
  if (data) return { ok: true, data: { kind: "done", created: data.created } };
  const problems = (error as { problems?: components["schemas"]["ImportProblemOut"][] } | undefined)
    ?.problems;
  if (response.status === 422 && Array.isArray(problems)) {
    return { ok: true, data: { kind: "invalid", problems } };
  }
  return failure(error, response.status);
}
