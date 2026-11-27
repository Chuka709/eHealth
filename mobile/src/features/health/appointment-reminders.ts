/**
 * Local reminders of the user's own appointments (docs/03 `reminder_offsets_min`: 1 day and 2
 * hours before by default) - planned with the dose reminders, in the same iOS 64-slot budget:
 * 56 doses + 1 "renew" + APPOINTMENT_BUDGET here, the rest for "10 мин дараа".
 *
 * Lock screen (H10): by default only "Танд товлол байна" and the time - never the title, place
 * or kind (a "biopsy" is health information); the details only when the user chose to show
 * names. `data` carries ids only.
 */

import { GRACE } from "@/features/meds/reminders";

export const APPOINTMENT_BUDGET = 5;
const AHEAD = 60 * 86_400_000; // reminders for appointments up to 60 days ahead

export type ReminderAppointment = {
  id: string;
  title: string;
  place: string | null;
  scheduledAt: number; // epoch ms
  offsetsMin: readonly number[];
  status: string;
};

export type AppointmentTexts = {
  title: string; // "Танд товлол байна"
  when: (at: number) => string; // "2026.11.12 09:00"
  named: (title: string, when: string, place: string | null) => string;
};

export type PlannedAppointmentReminder = {
  id: string;
  at: number;
  title: string;
  body: string;
  kind: "appointment";
  data: { kind: "appointment"; p: string; a: string };
  due: boolean;
};

export function planAppointmentReminders(
  input: {
    patientId: string;
    appointments: readonly ReminderAppointment[];
    now: number;
    showNames: boolean;
  },
  texts: AppointmentTexts,
): PlannedAppointmentReminder[] {
  const out: PlannedAppointmentReminder[] = [];
  for (const a of input.appointments) {
    if (
      a.status !== "planned" ||
      !Number.isFinite(a.scheduledAt) ||
      a.scheduledAt > input.now + AHEAD
    ) {
      continue;
    }
    for (const offset of new Set(a.offsetsMin)) {
      if (!Number.isInteger(offset) || offset < 0) continue;
      const at = a.scheduledAt - offset * 60_000;
      // still to come, or just passed (a late alarm is kept for GRACE, as for doses)
      if (at < input.now - GRACE || at > a.scheduledAt) continue;
      const when = texts.when(a.scheduledAt);
      const body = input.showNames ? texts.named(a.title, when, a.place) : when;
      out.push({
        // no profile or appointment id in the OS's own store of identifiers
        // a moved visit (same reminder moment, another time) or a new text is a new id
        id: `appt.${at}.${hash(`${input.patientId}|${a.id}|${a.scheduledAt}|${body}`)}`,
        at,
        title: texts.title,
        body,
        kind: "appointment",
        data: { kind: "appointment", p: input.patientId, a: a.id },
        due: at <= input.now,
      });
    }
  }
  out.sort((x, y) => x.at - y.at);
  // a reminder already fired (kept for a late alarm) does not take a future one's place
  const due = out.filter((n) => n.due);
  return [...due, ...out.filter((n) => !n.due).slice(0, APPOINTMENT_BUDGET)];
}

function hash(text: string): string {
  let h = 0x811c9dc5;
  for (let i = 0; i < text.length; i += 1) {
    h ^= text.charCodeAt(i);
    h = Math.imul(h, 0x01000193);
  }
  return (h >>> 0).toString(36);
}

const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/;
export const LOCAL_APPOINTMENT_ID = /^appt\.\d+\.[0-9a-z]+$/;

/** The ids an appointment reminder carries - checked, never trusted blindly. */
export function appointmentData(raw: unknown): { p: string; a: string } | null {
  if (typeof raw !== "object" || raw === null) return null;
  const { kind, p, a } = raw as { kind?: unknown; p?: unknown; a?: unknown };
  if (kind !== "appointment" || typeof p !== "string" || typeof a !== "string") return null;
  return UUID.test(p) && UUID.test(a) ? { p, a } : null;
}
