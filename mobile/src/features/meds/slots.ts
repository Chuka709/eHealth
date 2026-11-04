/**
 * Planned dose instants on the phone - the same rules as backend `core/slots.py` (H7, Q22),
 * checked against the same `packages/shared/fixtures/dose-slots.json`. Used offline for
 * today's doses and the local reminder schedule (decision (2) of the Phase 2 plan); nothing
 * here suggests, judges or changes a dose (CLAUDE.md rule 10).
 *
 * - "home" medications are on Ulaanbaatar time; "local" ones on the profile's zone in force.
 * - A zone switch never moves a dose that was already due before it: starting from
 *   Ulaanbaatar, switches apply oldest first, and a switch at T moves a dose only if it lies
 *   at or after T both before and after the move.
 * - A wall time is turned into an instant like Python's fold=0 (Temporal "compatible"): a
 *   repeated time (clocks back) is its first occurrence, a skipped one (clocks forward) takes
 *   the offset before the gap. Never JS Date's implicit local-time parsing.
 */

export const HOME_TIMEZONE = "Asia/Ulaanbaatar";

export type Mode = "home" | "local";

export type ScheduleTime = { at: string; amount?: string };
export type Schedule =
  | { type: "daily"; times: ScheduleTime[] }
  | { type: "weekly"; days: number[]; times: ScheduleTime[] }
  | { type: "prn" };

export type RegimenPlan = {
  effective_from: string; // YYYY-MM-DD
  seq: number;
  voided: boolean;
  schedule: Record<string, unknown>;
};

export type MedicationPlan = {
  mode: Mode;
  started_on: string | null;
  stopped_on: string | null; // the first day no longer taken (Q21)
  planned_end_on: string | null; // the last day of a course (inclusive)
  regimens: RegimenPlan[];
};

export type ZoneSwitch = { timezone: string; effective_at: string; seq: number };

export type Slot = {
  scheduledAt: number; // epoch ms, a whole minute
  localDay: string; // YYYY-MM-DD
  at: string; // "HH:MM" as written
  amount: string | null;
};

const HHMM = /^([01]\d|2[0-3]):[0-5]\d$/;
const MINUTE = 60_000;
const HOUR = 60 * MINUTE;
const DAY = 24 * HOUR;

const formatters = new Map<string, Intl.DateTimeFormat>();

function formatter(zone: string): Intl.DateTimeFormat {
  let found = formatters.get(zone);
  if (!found) {
    found = new Intl.DateTimeFormat("en-US", {
      timeZone: zone,
      hourCycle: "h23",
      year: "numeric",
      month: "2-digit",
      day: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
    });
    formatters.set(zone, found);
  }
  return found;
}

/** The zone's UTC offset at an instant, in ms (whole minutes). */
function offsetAt(zone: string, instant: number): number {
  const parts = formatter(zone).formatToParts(new Date(instant));
  const get = (type: string) => Number(parts.find((p) => p.type === type)?.value);
  const asUtc = Date.UTC(get("year"), get("month") - 1, get("day"), get("hour"), get("minute"));
  return asUtc - Math.floor(instant / MINUTE) * MINUTE;
}

function wallMs(day: string, at: string): number {
  const [y, m, d] = day.split("-").map(Number);
  const [h, min] = at.split(":").map(Number);
  return Date.UTC(y, m - 1, d, h, min);
}

/** The instant of wall time `at` on `day` in `zone` (fold=0, see module doc). */
export function instant(day: string, at: string, zone: string): number {
  const wall = wallMs(day, at);
  const before = offsetAt(zone, wall - DAY);
  const after = offsetAt(zone, wall + DAY);
  const candidates = [wall - before, wall - after].filter(
    (t, i, all) => all.indexOf(t) === i && t + offsetAt(zone, t) === wall,
  );
  if (candidates.length === 0) return wall - before; // a skipped time: the offset before
  return Math.min(...candidates); // a repeated time: its first occurrence
}

/** Switches latest first; ones whose zone this phone cannot use are left out. */
export function orderZones(zones: readonly ZoneSwitch[]): { at: number; zone: string }[] {
  return zones
    .map((z) => ({ at: Date.parse(z.effective_at), zone: z.timezone, seq: z.seq }))
    .filter((z) => Number.isFinite(z.at) && zoneUsable(z.zone))
    .sort((a, b) => b.at - a.at || b.seq - a.seq)
    .map(({ at, zone }) => ({ at, zone }));
}

function zoneUsable(zone: string): boolean {
  try {
    formatter(zone);
    return true;
  } catch {
    return false;
  }
}

/** The instant of the dose written `at` on `day` (`zones` latest first). */
export function place(
  day: string,
  at: string,
  mode: Mode,
  zones: readonly { at: number; zone: string }[],
): number {
  let moment = instant(day, at, HOME_TIMEZONE);
  if (mode === "home") return moment;
  for (let i = zones.length - 1; i >= 0; i -= 1) {
    const { at: from, zone } = zones[i];
    if (moment >= from) {
      const moved = instant(day, at, zone);
      if (moved >= from) moment = moved;
    }
  }
  return moment;
}

export function takenOn(plan: MedicationPlan, day: string): boolean {
  return (
    (plan.started_on === null || plan.started_on <= day) &&
    (plan.stopped_on === null || day < plan.stopped_on) &&
    (plan.planned_end_on === null || day <= plan.planned_end_on)
  );
}

function isoWeekday(day: string): number {
  const wd = new Date(`${day}T00:00:00Z`).getUTCDay();
  return wd === 0 ? 7 : wd;
}

function timesOn(schedule: Record<string, unknown>, day: string): Record<string, unknown>[] {
  const kind = schedule.type;
  if (kind !== "daily" && kind !== "weekly") return [];
  if (kind === "weekly") {
    const days = schedule.days;
    if (!Array.isArray(days) || !days.includes(isoWeekday(day))) return [];
  }
  const times = schedule.times;
  return Array.isArray(times)
    ? times.filter((t): t is Record<string, unknown> => typeof t === "object" && t !== null)
    : [];
}

function addDays(day: string, n: number): string {
  return new Date(Date.parse(`${day}T00:00:00Z`) + n * DAY).toISOString().slice(0, 10);
}

/** Switches that can place a dose of `day` (latest first); see backend `_near`. */
function near(
  oldestFirst: readonly { at: number; zone: string }[],
  day: string,
): { at: number; zone: string }[] {
  const midnight = Date.parse(`${day}T00:00:00Z`);
  const first = midnight - 14 * HOUR;
  const last = midnight + 36 * HOUR;
  let lo = oldestFirst.findIndex((z) => z.at >= first);
  if (lo === -1) lo = oldestFirst.length;
  let hi = oldestFirst.findIndex((z) => z.at > last);
  if (hi === -1) hi = oldestFirst.length;
  return oldestFirst.slice(Math.max(lo - 1, 0), hi).reverse();
}

/** Planned doses with start <= scheduledAt < end (epoch ms), in time order. */
export function doseSlots(
  plan: MedicationPlan,
  zones: readonly ZoneSwitch[],
  start: number,
  end: number,
): Slot[] {
  const oldestFirst = orderZones(zones).reverse();
  const history = plan.regimens
    .filter((r) => !r.voided)
    .sort((a, b) =>
      a.effective_from === b.effective_from
        ? a.seq - b.seq
        : a.effective_from < b.effective_from
          ? -1
          : 1,
    );
  const out: Slot[] = [];
  const last = new Date(end + DAY).toISOString().slice(0, 10);
  let i = 0;
  let inForce: RegimenPlan | null = null;
  for (let day = new Date(start - DAY).toISOString().slice(0, 10); day <= last; ) {
    while (i < history.length && history[i].effective_from <= day) {
      inForce = history[i];
      i += 1;
    }
    if (inForce && takenOn(plan, day)) {
      const zonesNear = near(oldestFirst, day);
      for (const item of timesOn(inForce.schedule, day)) {
        const at = item.at;
        const amount = item.amount;
        if (typeof at !== "string" || !HHMM.test(at)) continue;
        if (amount !== undefined && typeof amount !== "string") continue;
        const scheduledAt = place(day, at, plan.mode, zonesNear);
        if (start <= scheduledAt && scheduledAt < end) {
          out.push({ scheduledAt, localDay: day, at, amount: amount ?? null });
        }
      }
    }
    day = addDays(day, 1);
  }
  return out.sort((a, b) => a.scheduledAt - b.scheduledAt || (a.at < b.at ? -1 : 1));
}
