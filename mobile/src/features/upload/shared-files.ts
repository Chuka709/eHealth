import type { ShareIntentFile } from "expo-share-intent";

import { isForeignFile } from "@/features/upload/upload-files";
import type { Picked } from "@/features/upload/use-uploads";

const ACCEPTED = new Set([
  "application/pdf",
  "image/jpeg",
  "image/png",
  "image/heic",
  "image/heif",
  "image/webp",
]);

const OWN_PACKAGE = "mn.munkhly.labtrack";

/**
 * A content URI of this app's own providers (store and dev packages): another app sharing one
 * would have us read our own private files (security review 8.4 L3). The authority is parsed,
 * lowercased, and one with '@' (Android's "<userId>@<authority>") is refused outright.
 */
function isOwnProvider(path: string): boolean {
  const m = /^content:\/\/([^/?#]*)/i.exec(path);
  if (!m) return false;
  const authority = (m[1] ?? "").toLowerCase();
  return (
    authority.includes("@") || authority === OWN_PACKAGE || authority.startsWith(`${OWN_PACKAGE}.`)
  );
}

/**
 * A shared file's path as a file URI: each segment encoded on its own, so spaces, Cyrillic
 * letters (review M4) and also "#" and "?" (a name like "upload-queue#x.pdf" must not become
 * another file - security review 2026.11.27 M1) stay part of the name.
 */
export function sharedUri(path: string): string {
  if (path.startsWith("file://") || path.startsWith("content://")) return path;
  return `file://${path.split("/").map(encodeURIComponent).join("/")}`;
}

export type SharedNotice = "sharedUnreadable" | "sharedUnsupported" | null;

/**
 * Files shared from another app (Phase 3.5) that can be added, and what to say when none can.
 * An empty list means the other app's file could not be read (the B9 patch of expo-share-intent
 * skips such a file instead of crashing); otherwise the files were of a kind we do not take.
 */
export function readShared(files: readonly ShareIntentFile[] | null | undefined): {
  picked: Picked[];
  notice: SharedNotice;
} {
  const picked = (files ?? [])
    .filter((f) => f.mimeType !== null && ACCEPTED.has(f.mimeType))
    .filter((f) => !isOwnProvider(f.path))
    .filter((f) => isForeignFile(f.path.startsWith("/") ? `file://${f.path}` : f.path))
    .map((f) => ({ uri: sharedUri(f.path), mime: f.mimeType }));
  if (picked.length > 0) return { picked, notice: null };
  return { picked, notice: files?.length === 0 ? "sharedUnreadable" : "sharedUnsupported" };
}
