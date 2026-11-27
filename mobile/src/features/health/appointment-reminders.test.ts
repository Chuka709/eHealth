import {
  APPOINTMENT_BUDGET,
  appointmentData,
  planAppointmentReminders,
  type ReminderAppointment,
} from "./appointment-reminders";

const NOW = Date.parse("2026-11-05T01:00:00Z");
const P = "00000000-0000-4000-8000-0000000000aa";
const A = "11111111-1111-4111-8111-111111111111";
const texts = {
  title: "Танд товлол байна",
  when: (at: number) => new Date(at).toISOString().slice(0, 16),
  named: (title: string, when: string, place: string | null) =>
    [title, when, place].filter(Boolean).join(" · "),
};
const appt = (extra: Partial<ReminderAppointment> = {}): ReminderAppointment => ({
  id: A,
  title: "Бөөрний биопси",
  place: "Улсын нэгдүгээр төв эмнэлэг",
  scheduledAt: Date.parse("2026-11-07T01:00:00Z"),
  offsetsMin: [1440, 120],
  status: "planned",
  ...extra,
});
const plan = (appointments: ReminderAppointment[], showNames = false, now = NOW) =>
  planAppointmentReminders({ patientId: P, appointments, now, showNames }, texts);

test("a day and two hours before, by default", () => {
  const list = plan([appt()]);
  expect(list.map((n) => new Date(n.at).toISOString())).toEqual([
    "2026-11-06T01:00:00.000Z",
    "2026-11-06T23:00:00.000Z",
  ]);
  expect(list[0].data).toEqual({ kind: "appointment", p: P, a: A });
});

test("nothing about the visit on the lock screen unless names are shown (H10)", () => {
  const [hidden] = plan([appt()]);
  expect(hidden.title).toBe("Танд товлол байна");
  expect(JSON.stringify(hidden)).not.toMatch(/биопси|эмнэлэг/i);
  expect(hidden.id).not.toContain(A);
  expect(hidden.id).not.toContain(P);
  const [named] = plan([appt()], true);
  expect(named.body).toContain("Бөөрний биопси");
  expect(named.id).not.toBe(hidden.id);
});

test("done, cancelled, far away or passed appointments remind of nothing", () => {
  expect(plan([appt({ status: "done" })])).toEqual([]);
  expect(plan([appt({ status: "cancelled" })])).toEqual([]);
  expect(plan([appt({ scheduledAt: NOW + 90 * 86_400_000 })])).toEqual([]);
  // only the 2-hour reminder is still ahead
  const soon = plan([appt({ scheduledAt: NOW + 3 * 3_600_000 })]);
  expect(soon).toHaveLength(1);
});

test("at most the budget, earliest first", () => {
  const many = Array.from({ length: 6 }, (_, i) =>
    appt({
      id: `11111111-1111-4111-8111-11111111111${i}`,
      scheduledAt: NOW + (i + 2) * 86_400_000,
    }),
  );
  const list = plan(many);
  expect(list).toHaveLength(APPOINTMENT_BUDGET);
  const times = list.map((n) => n.at);
  expect(times).toEqual([...times].sort((x, y) => x - y));
});

test("a moved appointment gets new reminders even at the same moment (security review M1)", () => {
  const [first] = plan([appt({ offsetsMin: [1440] })]);
  const moved = plan([
    appt({ scheduledAt: Date.parse("2026-11-08T01:00:00Z"), offsetsMin: [2880] }),
  ]);
  expect(moved[0].at).toBe(first.at);
  expect(moved[0].id).not.toBe(first.id);
});

test("a broken date or offset plans nothing for it", () => {
  expect(plan([appt({ scheduledAt: Number.NaN })])).toEqual([]);
  expect(plan([appt({ offsetsMin: [-5, 1.5] })])).toEqual([]);
});

test("only well-formed ids are taken from a reminder", () => {
  expect(appointmentData({ kind: "appointment", p: P, a: A })).toEqual({ p: P, a: A });
  expect(appointmentData({ kind: "appointment", p: P, a: "../x" })).toBeNull();
  expect(appointmentData({ kind: "dose", p: P, a: A })).toBeNull();
});
