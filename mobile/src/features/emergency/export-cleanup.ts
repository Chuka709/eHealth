import { Directory, Paths } from "expo-file-system";

/**
 * Where the emergency card's exported files live, and how they are removed. Kept apart from
 * export-files.ts so that sign-out (features/auth/session.ts) can clear them without a require
 * cycle: export-files reads the session epoch.
 */

export const exportFolder = () => new Directory(Paths.cache, "emergency-export");
const printFolder = () => new Directory(Paths.cache, "Print"); // expo-print writes here first

export const removeQuietly = (item: () => { exists: boolean; delete: () => void }) => {
  try {
    const found = item();
    if (found.exists) found.delete();
  } catch {
    // already gone, or the system cleared the cache itself
  }
};

/** Removes every file made earlier (sign-out, a new export, a fresh signed-in start). */
export function clearExports(): void {
  removeQuietly(exportFolder);
  removeQuietly(printFolder);
}

/** expo-print's working folder only (after its file was moved out). */
export function clearPrintFolder(): void {
  removeQuietly(printFolder);
}
