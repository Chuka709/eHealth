import { useQuery } from "@tanstack/react-query";
import * as DocumentPicker from "expo-document-picker";
import { File } from "expo-file-system";
import * as ImagePicker from "expo-image-picker";
import DocumentScanner, { ResponseType } from "react-native-document-scanner-plugin";

import { currentEpoch } from "@/features/auth/session";
import { api, authFetch } from "@/lib/api";
import { apiBaseUrl } from "@/lib/api-base";
import { queryClient } from "@/lib/query-client";
import { newClientId } from "@/lib/random";

import { EXTENSIONS, removeSharedCopy, removeSourceCopy } from "./upload-files";
import {
  enqueueUpload,
  failedUploads,
  flushUploads,
  type PendingUpload,
  pendingUploads,
  tidyUploadFolder,
} from "./upload-queue";

export type Picked = { uri: string; mime: string };

/** Pages from the camera's document scanner (edges found, cropped); JPEG, never the gallery. */
export async function scanPages(): Promise<Picked[]> {
  const result = await DocumentScanner.scanDocument({
    maxNumDocuments: 10,
    croppedImageQuality: 90,
    responseType: ResponseType.ImageFilePath,
  });
  if (result.status !== "success") return [];
  return (result.scannedImages ?? []).map((uri) => ({
    uri: uri.startsWith("file://") ? uri : `file://${uri}`,
    mime: "image/jpeg",
  }));
}

/** Pictures already on the phone (the system photo picker: no gallery permission needed). */
export async function pickPictures(): Promise<Picked[]> {
  const result = await ImagePicker.launchImageLibraryAsync({
    mediaTypes: ["images"],
    allowsMultipleSelection: true,
    selectionLimit: 10,
    quality: 1,
    exif: false,
  });
  if (result.canceled) return [];
  return result.assets.map((a) => ({ uri: a.uri, mime: a.mimeType ?? "image/jpeg" }));
}

/** A PDF from files (or another app's storage provider). */
export async function pickPdf(): Promise<Picked[]> {
  const result = await DocumentPicker.getDocumentAsync({
    type: "application/pdf",
    copyToCacheDirectory: true,
    multiple: false,
  });
  if (result.canceled) return [];
  return result.assets.map((a) => ({ uri: a.uri, mime: a.mimeType ?? "application/pdf" }));
}

/** Each file becomes its own document; ids are made here so a retry is the same upload. */
export async function queueFiles(
  files: readonly Picked[],
  patientId: string,
  { shared = false }: { shared?: boolean } = {},
): Promise<"queued" | "full"> {
  const epoch = currentEpoch();
  try {
    for (const file of files) {
      const outcome = await enqueueUpload(file, patientId, newClientId(), epoch);
      if (outcome === "full") return "full";
    }
  } finally {
    // the scanner's or picker's own copies: ours are enough, and a full queue or a failed copy
    // leaves none of them behind either (security review 8.5 L2). A shared file: only the share
    // library's copy straight in the cache - another app chose that path (security review 3.5)
    for (const file of files) (shared ? removeSharedCopy : removeSourceCopy)(file.uri);
  }
  void queryClient.invalidateQueries({ queryKey: ["uploads"] });
  void sendWaitingUploads();
  return "queued";
}

export function sendUpload(upload: PendingUpload): Promise<Response> {
  const body = new FormData();
  body.append("client_id", upload.id);
  // the file itself (expo-file-system's File is a Blob): SDK 58's fetch refuses the old
  // { uri, name, type } part ("Unsupported FormDataPart implementation", found on the emulator)
  body.append("file", new File(upload.uri), `upload.${EXTENSIONS[upload.mime] ?? "bin"}`);
  return authFetch(`${apiBaseUrl}/api/v1/patients/${upload.patientId}/documents`, {
    method: "POST",
    body,
  });
}

export async function sendWaitingUploads(): Promise<number> {
  await tidyUploadFolder().catch(() => undefined);
  const sent = await flushUploads(sendUpload).catch(() => 0);
  void queryClient.invalidateQueries({ queryKey: ["uploads"] });
  if (sent > 0) void queryClient.invalidateQueries({ queryKey: ["documents"] });
  return sent;
}

/** Files still on the phone (waiting, or refused by the server) - for every profile. */
export function useUploadQueue() {
  return useQuery({
    queryKey: ["uploads"],
    queryFn: async () => ({ pending: await pendingUploads(), failed: await failedUploads() }),
    networkMode: "always",
  });
}

export type DocumentItem = Awaited<ReturnType<typeof listDocuments>>[number];

async function listDocuments(patientId: string) {
  const { data, error } = await api.GET("/api/v1/patients/{patient_id}/documents", {
    params: { path: { patient_id: patientId } },
  });
  if (error || !data) throw error ?? new Error("documents");
  return data;
}

const WORKING = new Set(["uploaded", "queued", "processing"]);

/** A profile's documents; polled while one is still being checked or read. */
export function useDocuments(patientId: string | undefined) {
  return useQuery({
    queryKey: ["documents", patientId],
    queryFn: () => listDocuments(patientId as string),
    enabled: patientId !== undefined,
    refetchInterval: (query) =>
      query.state.data?.some((d) => WORKING.has(d.status)) ? 5000 : false,
  });
}
