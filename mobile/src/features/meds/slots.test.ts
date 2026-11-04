import fixtures from "@labtrack/shared/fixtures/dose-slots.json";
import fc from "fast-check";

import { doseSlots, type MedicationPlan, orderZones, place, type ZoneSwitch } from "./slots";

type Case = (typeof fixtures.cases)[number];

describe("dose slots - the shared fixtures (same file as backend core/slots.py)", () => {
  it.each(fixtures.cases.map((c) => [c.name, c] as const))("%s", (_, c: Case) => {
    const slots = doseSlots(
      c.plan as MedicationPlan,
      c.zones as ZoneSwitch[],
      Date.parse(c.from),
      Date.parse(c.to),
    );
    expect(
      slots.map((s) => ({
        scheduled_at: new Date(s.scheduledAt).toISOString().replace(".000Z", "Z"),
        amount: s.amount,
      })),
    ).toEqual(c.expected);
  });
});

const ZONES = [
  "Asia/Ulaanbaatar",
  "Asia/Seoul",
  "Asia/Kolkata",
  "Europe/Istanbul",
  "America/New_York",
  "Asia/Kathmandu",
  "Pacific/Kiritimati",
  "Pacific/Pago_Pago",
  "Australia/Lord_Howe",
];
const START = Date.parse("2026-10-01T00:00:00Z");
const times = fc.uniqueArray(
  fc
    .tuple(fc.integer({ min: 0, max: 23 }), fc.integer({ min: 0, max: 59 }))
    .map(([h, m]) => `${String(h).padStart(2, "0")}:${String(m).padStart(2, "0")}`),
  { minLength: 1, maxLength: 4 },
);
const switches = fc
  .array(fc.tuple(fc.constantFrom(...ZONES), fc.integer({ min: 0, max: 60 * 24 * 60 })), {
    maxLength: 4,
  })
  .map((list) =>
    list.map(([timezone, minutes], seq) => ({
      timezone,
      effective_at: new Date(START + minutes * 60_000).toISOString(),
      seq,
    })),
  );

const daily = (at: string[]): MedicationPlan => ({
  mode: "local",
  started_on: null,
  stopped_on: null,
  planned_end_on: null,
  regimens: [
    {
      effective_from: "2026-01-01",
      seq: 1,
      voided: false,
      schedule: { type: "daily", times: [...at].sort().map((a) => ({ at: a, amount: "1" })) },
    },
  ],
});

describe("dose slots - properties", () => {
  it("one dose per day and time across any switches (H7)", () => {
    fc.assert(
      fc.property(times, switches, (at, zones) => {
        const slots = doseSlots(daily(at), zones, START, START + 40 * 86_400_000);
        const keys = new Set(slots.map((s) => `${s.localDay} ${s.at}`));
        expect(keys.size).toBe(slots.length);
        for (let d = 3; d < 37; d += 1) {
          const day = new Date(START + d * 86_400_000).toISOString().slice(0, 10);
          for (const a of at) expect(keys.has(`${day} ${a}`)).toBe(true);
        }
      }),
      { numRuns: 60 },
    );
  });

  it("a new switch never moves a dose already due (medical review H1)", () => {
    fc.assert(
      fc.property(
        times,
        switches,
        fc.constantFrom(...ZONES),
        fc.integer({ min: 0, max: 24 * 50 }),
        (at, zones, extra, hours) => {
          const latest = Math.max(START, ...zones.map((z) => Date.parse(z.effective_at)));
          const when = Math.max(latest, START + hours * 3_600_000);
          const more = [
            ...zones,
            { timezone: extra, effective_at: new Date(when).toISOString(), seq: zones.length },
          ];
          const end = START + 50 * 86_400_000;
          const before = doseSlots(daily(at), zones, START, end).filter(
            (s) => s.scheduledAt < when,
          );
          const after = doseSlots(daily(at), more, START, end).filter((s) => s.scheduledAt < when);
          expect(after).toEqual(before);
        },
      ),
      { numRuns: 60 },
    );
  });

  it("only nearby switches are walked, with the full walk's result", () => {
    fc.assert(
      fc.property(times, switches, (at, zones) => {
        const all = orderZones(zones);
        for (const s of doseSlots(daily(at), zones, START, START + 40 * 86_400_000)) {
          expect(place(s.localDay, s.at, "local", all)).toBe(s.scheduledAt);
        }
      }),
      { numRuns: 40 },
    );
  });
});
