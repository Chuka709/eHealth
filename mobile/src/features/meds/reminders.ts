/**
 * The local reminder schedule - a pure function of the cached medicines and zone (H6, H7,
 * H10; docs/08 "Сануулгын найдвартай байдал"). Reminders are the user's own schedule; nothing
 * here suggests or judges a dose (CLAUDE.md rule 10).
 *
 * - One notification per minute: doses due at the same minute (several medicines, or two
 *   times of one medicine brought together by a zone switch - Q26) share it and list every
 *   item, never only the first.
 * - iOS keeps at most 64 pending local notifications: 56 for doses, 8 left for appointments and
 *   "10 мин дараа". Each dose time takes two (its reminder and the repeat 15 minutes later,
 *   while the dose is not recorded). Days planned = min(7, floor(56 / (2 × the busiest day's
 *   times))); the phone re-plans on every app start and foreground, so the window keeps rolling.
 * - A day before the window runs out, one "open the app" notification: if the app is not
 *   opened, reminders would stop silently otherwise.
 * - A dose already recorded (taken early, skipped ahead, by a caregiver) is not reminded:
 *   a reminder after "Уусан" invites a second dose (medical review 2.5c H-1). Of a shared
 *   minute only the unrecorded doses stay.
 * - A reminder whose time has just passed is kept for GRACE, never cancelled by a re-plan
 *   before it fires: without the exact-alarm permission Android may hold it back by up to an
 *   hour (window +1h, measured on the emulator in 2.10d - H18).
 * - One notification per dose time, its title the scheduled time ("08:00-ийн эмийн
 *   сануулга") and its text the medicines with amounts - unless the user turned names off
 *   ("2 тун"). Lock screen (H10): the channels are PRIVATE (and iOS hides previews when
 *   locked), the title never names a medicine. `data` carries ids and instants only.
 */

import type { MedicationPlan, Slot, ZoneSwitch } from "./slots";
import { doseSlots } from "./slots";

export const DOSE_BUDGET = 56;
export const MAX_DAYS = 7;
export const GRACE = 75 * 60_000; // the +1h inexact window, with a margin
/** the one repeat of an unrecorded dose's reminder */
export const REPEAT = 15 * 60_000;
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
  /** plan the repeat 15 minutes later - not where the order of alarms is not sure: Android
   * without exact alarms may hold each back by up to an hour, so a repeat could come before
   * its reminder and read as a new dose (medical review M3, H18) */
  repeat?: boolean;
};

export type ReminderTexts = {
  title: string; // "Эм уух цаг боллоо" (the "open the app" one, iOS preview placeholder)
  /** a dose reminder's title with its scheduled time: "08:00-ийн эмийн сануулга" - a reminder
   * held back (inexact alarm, up to an hour or more) still says which dose it is (H18) */
  timedTitle: (time: string) => string;
  /** the repeat says the dose is not marked yet, never "take it again" (medical review M1):
   * "Тэмдэглэгдээгүй: 08:00-ийн эмийн сануулга" / "Уусан бол «Уусан» дарна уу. 2 тун" */
  again: (title: string) => string;
  againBody: (body: string) => string;
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
  // each dose time takes two: the reminder and its repeat
  const days = daysFor(busiest * 2);
  const end = start + days * DAY;
  // a late one (and its repeat) still pending on the OS counts against the same 64
  const room = Math.max(0, Math.floor(DOSE_BUDGET / 2) - late.length);
  const groups = week.filter((g) => g.at < end).slice(0, room);

  const reminders: PlannedNotification[] = [...late, ...groups].map((g) => {
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
    // the time as written on the regimen (two times of one minute after a zone switch: both)
    const title = texts.timedTitle([...new Set(g.items.map(({ slot }) => slot.at))].join(" / "));
    const content = `${input.showNames ? "n" : "a"}|${title}|${body}|${d.map((x) => x.m).join(",")}`;
    return {
      // no profile id in the OS's own (unencrypted) store of identifiers
      id: `dose.${g.at}.${hash(`${input.patientId}|${content}`)}`,
      at: g.at,
      title,
      body,
      kind: "dose",
      data: { kind: "dose", p: input.patientId, d },
      due: g.at <= input.now,
    };
  });
  // once more REPEAT later while the dose is not recorded (the user's choice 2026.11.19): a
  // recorded dose drops out of the plan, and its repeat is cancelled with it
  const repeat = input.repeat ?? true;
  const out: PlannedNotification[] = reminders.flatMap((r) =>
    repeat && r.at + REPEAT > input.now
      ? [
          r,
          {
            ...r,
            id: `again.${r.id}`,
            at: r.at + REPEAT,
            title: texts.again(r.title),
            body: texts.againBody(r.body),
            due: false,
          },
        ]
      : [r],
  );

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
