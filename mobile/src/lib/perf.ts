/**
 * Phase 6 DoD timing (docs/01: Home p95 < 1.5 s on a mid-range Android): how long from the
 * app's JS start until Home shows its lab part with data. Only in development, or in a build
 * made with EXPO_PUBLIC_PERF_LOG=1 for the measurement (read with `adb logcat | grep perf:`).
 * It writes a name and milliseconds - never a value, name or id (CLAUDE.md rule 3).
 */
const start = Date.now();
const done = new Set<string>();

export const perfLogging = __DEV__ || process.env.EXPO_PUBLIC_PERF_LOG === "1";

/** Logs `perf:<name> <ms>` once per app start. */
export function markOnce(name: string): void {
  if (!perfLogging || done.has(name)) return;
  done.add(name);
  console.log(`perf:${name} ${Date.now() - start}`);
}
