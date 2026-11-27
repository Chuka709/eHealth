import { useEffect } from "react";

import { api } from "@/lib/api";

import { useReminderHealth } from "./use-reminder-health";

/**
 * This device tells the server whether its medicine reminders can come on time (Q48): Android
 * without the exact-alarm permission can show them up to about an hour late, so a caregiver's
 * dose alert then waits at least 90 minutes (0046). Sent when known and whenever it changes
 * (the health is re-read on every return to the app); unknown is never sent. Silent on failure.
 */
let lastSent: boolean | null = null;

/** Sign-out (and tests): the next account sends its state at once. */
export function resetDeviceAlarmReport(): void {
  lastSent = null;
}

export function useDeviceAlarmReport(): void {
  const health = useReminderHealth();
  const exactOff = health.data?.exactOff;
  useEffect(() => {
    if (exactOff === null || exactOff === undefined) return;
    const exact = !exactOff;
    if (lastSent === exact) return;
    lastSent = exact;
    void api
      .PUT("/api/v1/me/device-alarms", { body: { exact_alarms: exact } })
      .then(({ response }) => {
        if (!response.ok) lastSent = null; // try again on the next return
      })
      .catch(() => {
        lastSent = null;
      });
  }, [exactOff]);
}
