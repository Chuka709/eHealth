import fc from "fast-check";

import {
  DOSE_BUDGET,
  daysFor,
  GRACE,
  MAX_DAYS,
  planReminders,
  type ReminderMedicine,
  type ReminderTexts,
} from "./reminders";
import type { MedicationPlan } from "./slots";

const texts: ReminderTexts = {
  title: "Эм уух цаг боллоо",
  timedTitle: (time) => `${time}-ийн эмийн сануулга`,
  count: (n) => `${n} тун`,
  item: (name, amount) => (amount ? `${name} ${amount}` : name),
  renewTitle: "Сануулгаа сэргээнэ үү",
  renewBody: "Апп-аа нээж сануулгаа сэргээнэ үү.",
};
const NOW = Date.parse("2026-11-04T03:00:00Z"); // 11:00 Ulaanbaatar
const DAY = 86_400_000;

const plan = (times: string[], extra: Partial<MedicationPlan> = {}): MedicationPlan => ({
  mode: "home",
  started_on: null,
  stopped_on: null,
  planned_end_on: null,
  regimens: [
    {
      effective_from: "2026-01-01",
      seq: 1,
      voided: false,
      schedule: { type: "daily", times: times.map((at) => ({ at, amount: "2" })) },
    },
  ],
  ...extra,
});
const med = (
  id: string,
  times: string[],
  extra: Partial<MedicationPlan> = {},
): ReminderMedicine => ({
  id,
  name: `Эм ${id}`,
  unit: "мг",
  plan: plan(times, extra),
});
const input = (medicines: ReminderMedicine[], showNames = false) => ({
  patientId: "p1",
  medicines,
  zones: [],
  now: NOW,
  showNames,
  recorded: new Set<string>(),
});

describe("reminder planning", () => {
  it("plans 7 days when they fit, fewer when a day is busy (iOS 64 limit)", () => {
    expect(daysFor(2)).toBe(7);
    expect(daysFor(8)).toBe(7);
    expect(daysFor(10)).toBe(5); // docs/08: 5 medicines x 2 = 10 a day -> 5 days
    expect(daysFor(56)).toBe(1);
    expect(daysFor(80)).toBe(1);
  });

  it("names nothing on the lock screen unless the user chose so (H10)", () => {
    const [first] = planReminders(input([med("a", ["20:00"])]), texts);
    // the scheduled time, never a name: a reminder held back still says which dose (H18)
    expect(first.title).toBe("20:00-ийн эмийн сануулга");
    expect(first.body).toBe("1 тун");
    expect(JSON.stringify(first)).not.toContain("Эм a");
    expect(first.data).toEqual({ kind: "dose", p: "p1", d: [{ m: "a", at: first.at }] });
    const [named] = planReminders(input([med("a", ["20:00"])], true), texts);
    expect(named.body).toBe("Эм a 2 мг");
    expect(named.id).not.toBe(first.id); // a change of content replaces the notification
  });

  it("one notification per minute lists every dose due then", () => {
    const list = planReminders(input([med("a", ["20:00"]), med("b", ["20:00"])], true), texts);
    const first = list[0];
    expect(first.body).toBe("Эм a 2 мг, Эм b 2 мг");
    expect(first.data.d.map((x) => x.m)).toEqual(["a", "b"]);
  });

  it("stops after a course ends and plans the new dose from its first day", () => {
    const course = med("c", ["08:00"], { planned_end_on: "2026-11-06" });
    const doses = planReminders(input([course]), texts).filter((n) => n.kind === "dose");
    expect(doses.map((n) => new Date(n.at).toISOString())).toEqual([
      "2026-11-05T00:00:00.000Z",
      "2026-11-06T00:00:00.000Z",
    ]);
  });

  it("asks to open the app a day before the planned reminders run out", () => {
    const list = planReminders(input([med("a", ["08:00", "20:00"])]), texts);
    const renew = list.filter((n) => n.kind === "renew");
    expect(renew).toHaveLength(1);
    const lastDose = Math.max(...list.filter((n) => n.kind === "dose").map((n) => n.at));
    expect(renew[0].at).toBe(lastDose - DAY);
  });

  it("never more than 56 dose notifications, none in the past, all in time order", () => {
    const at = fc.uniqueArray(
      fc
        .tuple(fc.integer({ min: 0, max: 23 }), fc.integer({ min: 0, max: 59 }))
        .map(([h, m]) => `${String(h).padStart(2, "0")}:${String(m).padStart(2, "0")}`),
      { minLength: 1, maxLength: 12 },
    );
    fc.assert(
      fc.property(fc.array(at, { minLength: 1, maxLength: 8 }), (schedules) => {
        const list = planReminders(
          input(schedules.map((times, i) => med(String(i), times))),
          texts,
        );
        const doses = list.filter((n) => n.kind === "dose");
        expect(doses.length).toBeLessThanOrEqual(DOSE_BUDGET);
        expect(list.length).toBeLessThanOrEqual(DOSE_BUDGET + 1);
        for (const n of list) {
          expect(n.at).toBeGreaterThanOrEqual(NOW - GRACE);
          expect(n.at).toBeLessThan(NOW + MAX_DAYS * DAY + 1);
        }
        const times = doses.map((n) => n.at);
        expect(times).toEqual([...times].sort((x, y) => x - y));
        expect(new Set(list.map((n) => n.id)).size).toBe(list.length);
      }),
      { numRuns: 50 },
    );
  });

  it("nothing for stopped medicines", () => {
    expect(
      planReminders(input([med("s", ["20:00"], { stopped_on: "2026-11-01" })]), texts),
    ).toEqual([]);
  });
});

describe("doses already recorded and late alarms (medical review 2.5c)", () => {
  it("a dose recorded early is not reminded; the rest of its minute is", () => {
    const base = input([med("a", ["20:00"]), med("b", ["20:00"])]);
    const [first] = planReminders(base, texts);
    const recorded = new Set([`a@${first.at}`]);
    const [after] = planReminders({ ...base, recorded }, texts);
    expect(after.at).toBe(first.at);
    expect(after.data.d.map((x) => x.m)).toEqual(["b"]);
    expect(after.id).not.toBe(first.id);
    const both = new Set([`a@${first.at}`, `b@${first.at}`]);
    expect(planReminders({ ...base, recorded: both }, texts)[0].at).toBeGreaterThan(first.at);
  });

  it("a reminder whose time just passed stays planned (late alarm), marked due", () => {
    const at = Date.parse("2026-11-04T12:00:00Z"); // 20:00 Ulaanbaatar
    const late = planReminders({ ...input([med("a", ["20:00"])]), now: at + 5 * 60_000 }, texts);
    expect(late[0]).toMatchObject({ at, due: true });
    // an inexact alarm may be held back up to an hour (H18): still kept then
    const held = planReminders({ ...input([med("a", ["20:00"])]), now: at + 59 * 60_000 }, texts);
    expect(held[0]).toMatchObject({ at, due: true });
    const gone = planReminders(
      { ...input([med("a", ["20:00"])]), now: at + GRACE + 60_000 },
      texts,
    );
    expect(gone[0].at).toBeGreaterThan(at);
  });

  it("identifiers carry no profile id", () => {
    for (const n of planReminders(input([med("a", ["20:00"])]), texts)) {
      expect(n.id).not.toContain("p1");
    }
  });
});
