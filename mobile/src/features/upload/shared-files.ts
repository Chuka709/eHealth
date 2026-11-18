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

// This app's own content providers (file provider, store and dev packages): another app that
// shares such a URI would have us read our own private files (security review 8.4 L3).
const OWN_PROVIDER = /^content:\/\/mn\.munkhly\.labtrack(\.|\/)/;

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
    .filter((f) => !OWN_PROVIDER.test(f.path))
    .filter((f) => isForeignFile(f.path.startsWith("/") ? `file://${f.path}` : f.path))
    .map((f) => ({
      // a plain path may hold spaces or Cyrillic letters: encoded into a file URI (review M4)
      uri:
        f.path.startsWith("file://") || f.path.startsWith("content://")
          ? f.path
          : `file://${encodeURI(f.path)}`,
      mime: f.mimeType,
    }));
  if (picked.length > 0) return { picked, notice: null };
  return { picked, notice: files?.length === 0 ? "sharedUnreadable" : "sharedUnsupported" };
}
