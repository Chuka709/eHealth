import { Directory, File, Paths } from "expo-file-system";

/**
 * Picked and scanned files wait for the network in the app's own cache folder (Phase 3.4):
 * never in the photo gallery or a shared folder (CLAUDE.md rule 8); the cache is in no backup
 * on either platform (iOS Caches, and the Android backup rules exclude every domain). The
 * system may clear a cache under storage pressure: a file gone before it was sent is reported
 * to the user (upload-queue.ts "file_missing"), never sent empty. Removed once sent, and the
 * whole cache on sign-out. Kept apart from upload-queue.ts so sign-out
 * (features/auth/session.ts) can clear it without a require cycle.
 */
export const uploadFolder = () => new Directory(Paths.cache, "upload-queue");

export const EXTENSIONS: Record<string, string> = {
  "application/pdf": "pdf",
  "image/jpeg": "jpg",
  "image/png": "png",
  "image/heic": "heic",
  "image/heif": "heif",
  "image/webp": "webp",
};

/** A private copy named by the upload's id (the original name is never kept). */
export function copyIn(sourceUri: string, id: string, mime: string): string {
  const folder = uploadFolder();
  if (!folder.exists) folder.create({ intermediates: true });
  const target = new File(folder, `${id}.${EXTENSIONS[mime] ?? "bin"}`);
  if (target.exists) target.delete();
  new File(sourceUri).copy(target);
  return target.uri;
}

export function fileExists(uri: string): boolean {
  try {
    return new File(uri).exists;
  } catch {
    return false;
  }
}

export function removeFile(uri: string): void {
  try {
    const file = new File(uri);
    if (file.exists) file.delete();
  } catch {
    // already gone
  }
}

/**
 * The picker's or scanner's own temporary copy, once ours exists: only inside this app's cache
 * (a file another app owns is never touched). Security review 3.4 (H2).
 */
export function removeSourceCopy(uri: string): void {
  const cache = Paths.cache.uri.replace(/\/?$/, "/");
  if (uri.startsWith(cache) && !uri.startsWith(uploadFolder().uri)) removeFile(uri);
}

/**
 * A file another app shared names its own path: never one inside this app's private data
 * (the encrypted store, the waiting files) - a malicious app could make the user upload them
 * (commit security review 3.5). The share library's copies in the cache are allowed, the
 * upload queue folder is not.
 */
export function isForeignFile(uri: string): boolean {
  if (uri.startsWith("content://")) return true;
  let path: string;
  try {
    path = decodeURI(uri.replace(/^file:\/\//, ""));
  } catch {
    return false;
  }
  if (path.split("/").includes("..")) return false;
  const local = (u: string) => decodeURI(u.replace(/^file:\/\//, "")).replace(/\/?$/, "/");
  const cache = local(Paths.cache.uri);
  const queue = local(uploadFolder().uri);
  if (path.startsWith(queue)) return false;
  if (path.startsWith(cache)) return true;
  // the app's data folder by name, so an alias of it (Android /data/data/<pkg> for
  // /data/user/0/<pkg>) is refused too; an alias of the cache is refused as well (fail closed)
  const appFolder = local(Paths.document.uri).split("/").filter(Boolean).at(-2);
  return appFolder !== undefined && !path.split("/").includes(appFolder);
}

/** Files in the folder that no waiting upload names (an app killed mid-copy, a wipe cut short). */
export function removeStrays(keep: ReadonlySet<string>): void {
  try {
    const folder = uploadFolder();
    if (!folder.exists) return;
    for (const item of folder.list()) {
      if (item instanceof File && !keep.has(item.uri)) item.delete();
    }
  } catch {
    // nothing to tidy
  }
}

/**
 * Sign-out: the waiting files and everything else in the app's cache - the scanner's pages, the
 * pickers' copies, a shared file, the emergency card's exports (security review 3.4 H2).
 */
export function clearUploads(): void {
  try {
    const folder = uploadFolder();
    if (folder.exists) folder.delete(); // the waiting files first, whatever else fails
  } catch {
    // already gone
  }
  try {
    for (const item of new Directory(Paths.cache).list()) {
      try {
        item.delete();
      } catch {
        // in use or already gone
      }
    }
  } catch {
    // nothing to remove
  }
}
