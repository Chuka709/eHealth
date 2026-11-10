import { Directory, File, Paths } from "expo-file-system";
import * as Sharing from "expo-sharing";

import { currentEpoch, isWiping } from "@/features/auth/session";

/**
 * Files made from the emergency card (wallet PDF, wallpaper image) leave the app only through
 * the share sheet: the user picks where they go (print, Files, Photos). The app never writes
 * them to the gallery or any shared folder itself (CLAUDE.md rule 8; user decision 2.7 (a)).
 * The temporary copy lives in one cache folder, under a fixed name (no name, no id). It is
 * emptied before the next export, once per run at the signed-in start, and on sign-out. It is
 * never deleted right after sharing, because the receiving app may still be reading it.
 * expo-print's own working folder is emptied with it.
 *
 * An export started before a sign-out (or another sign-in) is dropped: no file is kept and no
 * share sheet opens for an account that is gone.
 */

const folder = () => new Directory(Paths.cache, "emergency-export");
const printFolder = () => new Directory(Paths.cache, "Print"); // expo-print writes here first

const remove = (item: () => { exists: boolean; delete: () => void }) => {
  try {
    const found = item();
    if (found.exists) found.delete();
  } catch {
    // already gone, or the system cleared the cache itself
  }
};

/** Removes every file made earlier (sign-out, a new export, a fresh signed-in start). */
export function clearExports(): void {
  remove(folder);
  remove(printFolder);
}

let clearedThisRun = false;
/** Once per app process: unlocking again must not delete a file a share is still reading. */
export function clearExportsOnce(): void {
  if (clearedThisRun) return;
  clearedThisRun = true;
  clearExports();
}

/** Taken when an export starts; the export continues only while it is still valid. */
export type ExportTicket = { epoch: number };

export function startExport(): ExportTicket {
  return { epoch: currentEpoch() };
}

const stillValid = (ticket: ExportTicket) => ticket.epoch === currentEpoch() && !isWiping();

function freshFolder(): Directory {
  clearExports();
  const dir = folder();
  dir.create({ idempotent: true, intermediates: true });
  return dir;
}

/** Moves a just-made file into the export folder. The source never stays behind. */
export async function keepForSharing(
  ticket: ExportTicket,
  uri: string,
  name: string,
): Promise<File | null> {
  const source = new File(uri);
  if (!stillValid(ticket)) {
    remove(() => source);
    return null;
  }
  try {
    const file = source;
    await file.move(freshFolder());
    file.rename(name);
    return file;
  } catch (error) {
    remove(() => source);
    throw error;
  }
}

/** Writes bytes straight into the export folder (no temporary file elsewhere). */
export function writeForSharing(
  ticket: ExportTicket,
  bytes: Uint8Array,
  name: string,
): File | null {
  if (!stillValid(ticket)) return null;
  const file = new File(freshFolder(), name);
  file.create({ overwrite: true });
  file.write(bytes);
  return file;
}

/** "dropped": the session ended meanwhile (nothing to say); "unavailable": no share sheet. */
export type ShareResult = "shared" | "unavailable" | "dropped";

/** Opens the share sheet, if the export is still valid. */
export async function shareFile(
  ticket: ExportTicket,
  file: File | null,
  mimeType: "application/pdf" | "image/png",
): Promise<ShareResult> {
  if (!file || !stillValid(ticket)) {
    clearExports();
    return "dropped";
  }
  if (!(await Sharing.isAvailableAsync())) return "unavailable";
  await Sharing.shareAsync(file.uri, {
    mimeType,
    UTI: mimeType === "application/pdf" ? "com.adobe.pdf" : "public.png",
  });
  return "shared";
}
