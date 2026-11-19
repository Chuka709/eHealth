/** "Re-plan the reminders now" - after a dose is recorded or undone, a setting changed. */
const listeners = new Set<() => void>();

export function onReminderSync(run: () => void): () => void {
  listeners.add(run);
  return () => listeners.delete(run);
}

export function requestReminderSync(): void {
  for (const run of listeners) run();
}
