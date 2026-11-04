/**
 * The local reminder schedule - a pure function of the cached medicines and zone (H6, H7,
 * H10; docs/08 "Сануулгын найдвартай байдал"). Reminders are the user's own schedule; nothing
 * here suggests or judges a dose (CLAUDE.md rule 10).
 *
 * - One notification per minute: doses due at the same minute (several medicines, or two
 *   times of one medicine brought together by a zone switch - Q26) share it and list every
 *   item, never only the first.
 * - iOS keeps at most 64 pending local notifications: 56 for doses, 8 left for appointments and
 *   "10 мин дараа". Days planned = min(7, floor(56 / the busiest day's notifications)); the
 *   phone re-plans on every app start and foreground, so the window keeps rolling.
 * - A day before the window runs out, one "open the app" notification: if the app is not
 *   opened, reminders would stop silently otherwise.
 * - A dose already recorded (taken early, skipped ahead, by a caregiver) is not reminded:
 *   a reminder after "Уусан" invites a second dose (medical review 2.5c H-1). Of a shared
 *   minute only the unrecorded doses stay.
 * - A reminder whose time has just passed (an inexact Android alarm runs up to ~10 min late -
 *   H18) is kept for GRACE, never cancelled by a re-plan before it fires.
 * - Lock screen (H10): by default no medicine name anywhere in the notification - only "Эм уух
 *   цаг боллоо"; names only when the user chose so. `data` carries ids and instants only.
 */

import type { MedicationPlan, Slot, ZoneSwitch } from "./slots";
import { doseSlots } from "./slots";

export const DOSE_BUDGET = 56;
export const MAX_DAYS = 7;
export const GRACE = 30 * 60_000;
const DAY = 24 * 60 * 60_000;

export type ReminderMedicine = {
  id: string;
  name: string;
  unit: string | null; // shown after an amount ("мг")
  plan: MedicationPlan;
};

export type ReminderInput = {
  patientId: string;
  medicines: readonly ReminderMedicine[];
  zones: readonly ZoneSwitch[];
  now: number;
  showNames: boolean;
  /** doseKey(medicationId, scheduledAt) of doses already recorded */
  recorded: ReadonlySet<string>;
};

export type ReminderTexts = {
  title: string; // "Эм уух цаг боллоо"
  count: (n: number) => string; // "2 тун" (no names)
  item: (name: string, amount: string | null) => string; // "Такролимус 2 мг"
  renewTitle: string;
  renewBody: string;
};

export type DoseItem = { m: string; at: number }; // medication id, scheduled instant

export type PlannedNotification = {
  id: string; // stable for the same content: re-planning keeps unchanged ones
  at: number; // epoch ms
  title: string;
  body: string;
  kind: "dose" | "renew";
  data: { kind: "dose" | "renew"; p: string; d: DoseItem[] };
  /** already due (within GRACE): kept if still scheduled, never scheduled anew */
  due: boolean;
};

/** Days to plan when the busiest of the next 7 days has `perDay` notifications. */
export function daysFor(perDay: number): number {
  if (perDay <= 0) return MAX_DAYS;
  return Math.max(1, Math.min(MAX_DAYS, Math.floor(DOSE_BUDGET / perDay)));
}

type Group = { at: number; items: { med: ReminderMedicine; slot: Slot }[] };

function groupsBetween(input: ReminderInput, start: number, end: number): Group[] {
  const byMinute = new Map<number, Group>();
  for (const med of input.medicines) {
    for (const slot of doseSlots(med.plan, input.zones, start, end)) {
      if (input.recorded.has(`${med.id}@${slot.scheduledAt}`)) continue;
      const group = byMinute.get(slot.scheduledAt) ?? { at: slot.scheduledAt, items: [] };
      group.items.push({ med, slot });
      byMinute.set(slot.scheduledAt, group);
    }
  }
  return [...byMinute.values()].sort((a, b) => a.at - b.at);
}

export function planReminders(input: ReminderInput, texts: ReminderTexts): PlannedNotification[] {
  const start = input.now + 1;
  const late = groupsBetween(input, input.now - GRACE, start);
  const week = groupsBetween(input, start, start + MAX_DAYS * DAY);
  if (week.length === 0 && late.length === 0) return [];
  let busiest = 0;
  for (let d = 0; d < MAX_DAYS; d += 1) {
    const from = start + d * DAY;
    const n = week.filter((g) => g.at >= from && g.at < from + DAY).length;
    busiest = Math.max(busiest, n);
  }
  const days = daysFor(busiest);
  const end = start + days * DAY;
  // a late one still pending on the OS counts against the same 64
  const groups = week.filter((g) => g.at < end).slice(0, Math.max(0, DOSE_BUDGET - late.length));

  const out: PlannedNotification[] = [...late, ...groups].map((g) => {
    const d = g.items.map(({ med, slot }) => ({ m: med.id, at: slot.scheduledAt }));
    const body = input.showNames
      ? g.items
          .map(({ med, slot }) =>
            texts.item(
              med.name,
              slot.amount ? `${slot.amount}${med.unit ? ` ${med.unit}` : ""}` : null,
            ),
          )
          .join(", ")
      : texts.count(g.items.length);
    const content = `${input.showNames ? "n" : "a"}|${body}|${d.map((x) => x.m).join(",")}`;
    return {
      // no profile id in the OS's own (unencrypted) store of identifiers
      id: `dose.${g.at}.${hash(`${input.patientId}|${content}`)}`,
      at: g.at,
      title: texts.title,
      body,
      kind: "dose",
      data: { kind: "dose", p: input.patientId, d },
      due: g.at <= input.now,
    };
  });

  // a day before the planned doses run out (only when there is such a day ahead)
  const last = groups.at(-1)?.at ?? end;
  const renewAt = Math.min(end, last) - DAY;
  if (renewAt > input.now + 60 * 60_000) {
    out.push({
      id: `renew.${renewAt}.${hash(input.patientId)}`,
      at: renewAt,
      title: texts.renewTitle,
      body: texts.renewBody,
      kind: "renew",
      data: { kind: "renew", p: input.patientId, d: [] },
      due: false,
    });
  }
  return out;
}

/** A short stable hash (FNV-1a) - identifiers only, never shown. */
function hash(text: string): string {
  let h = 0x811c9dc5;
  for (let i = 0; i < text.length; i += 1) {
    h ^= text.charCodeAt(i);
    h = Math.imul(h, 0x01000193);
  }
  return (h >>> 0).toString(36);
}
