import * as Notifications from "expo-notifications";

import { showRemindersInForeground } from "@/lib/notifications";

import { snooze, syncReminders } from "./notify";
import type { PlannedNotification } from "./reminders";

type Scheduled = {
  identifier: string;
  content: { body?: string; data?: unknown };
  trigger: { date: number };
};
const os = (jest.requireMock("expo-notifications") as { __scheduled: Map<string, Scheduled> })
  .__scheduled;

const P = "00000000-0000-4000-8000-0000000000aa";
const A = "22222222-2222-4222-8222-222222222222";
const B = "33333333-3333-4333-8333-333333333333";

const dose = (id: string, at: number, d: string[], due = false): PlannedNotification => ({
  id,
  at,
  title: "Эм уух цаг боллоо",
  body: `${d.length} тун`,
  kind: "dose",
  data: { kind: "dose", p: P, d: d.map((m) => ({ m, at })) },
  due,
});

beforeEach(() => {
  os.clear();
  jest.clearAllMocks();
});

const always = () => true;
const keepAll = () => true;

test("an unchanged reminder is left alone, a removed one cancelled, a new one scheduled", async () => {
  const at = Date.now() + 3_600_000;
  await syncReminders([dose(`dose.${at}.a`, at, [A])], keepAll, always);
  expect([...os.keys()]).toEqual([`dose.${at}.a`]);
  await syncReminders(
    [dose(`dose.${at}.a`, at, [A]), dose(`dose.${at + 1}.b`, at + 1, [B])],
    keepAll,
    always,
  );
  expect(Notifications.scheduleNotificationAsync).toHaveBeenCalledTimes(2); // not re-scheduled
  await syncReminders([dose(`dose.${at + 1}.b`, at + 1, [B])], keepAll, always);
  expect([...os.keys()]).toEqual([`dose.${at + 1}.b`]);
});

test("a late alarm still pending is never cancelled by a re-plan (H18)", async () => {
  const at = Math.floor((Date.now() - 3 * 60_000) / 60_000) * 60_000; // due 3 min ago
  os.set(`dose.${at}.a`, { identifier: `dose.${at}.a`, content: {}, trigger: { date: at } });
  await syncReminders([dose(`dose.${at}.a`, at, [A, B], true)], keepAll, always);
  expect(os.has(`dose.${at}.a`)).toBe(true);
  expect(Notifications.cancelScheduledNotificationAsync).not.toHaveBeenCalled();
});

test("a late shared alarm whose content changed is replaced at once, not lost", async () => {
  const at = Math.floor((Date.now() - 3 * 60_000) / 60_000) * 60_000;
  os.set(`dose.${at}.ab`, { identifier: `dose.${at}.ab`, content: {}, trigger: { date: at } });
  // A was recorded in the app meanwhile: only B is left of that minute
  await syncReminders([dose(`dose.${at}.b`, at, [B], true)], keepAll, always);
  expect(os.has(`dose.${at}.ab`)).toBe(false);
  const replaced = os.get(`dose.${at}.b`);
  expect(replaced?.trigger.date).toBeGreaterThan(Date.now() - 1000);
});

test("a due reminder already gone (fired) is not shown again", async () => {
  const at = Math.floor((Date.now() - 3 * 60_000) / 60_000) * 60_000;
  await syncReminders([dose(`dose.${at}.a`, at, [A], true)], keepAll, always);
  expect(os.size).toBe(0);
});

test("a snooze is cancelled once its dose is recorded (medical review 2.5c H-2)", async () => {
  const at = Date.now() - 60_000;
  const data = { kind: "dose", p: P, d: [{ m: A, at: Math.floor(at / 60_000) * 60_000 }] };
  await snooze("dose.1.a", { title: "t", body: "1 тун", data }, always);
  expect(os.has("snooze.dose.1.a")).toBe(true);
  await syncReminders([], () => false, always);
  expect(os.has("snooze.dose.1.a")).toBe(false);
});

test("a sign-out during a sync leaves nothing scheduled (rule 8)", async () => {
  const at = Date.now() + 3_600_000;
  let calls = 0;
  const valid = () => {
    calls += 1;
    return calls < 3; // the session ends after the first reminder is scheduled
  };
  await syncReminders(
    [dose(`dose.${at}.a`, at, [A]), dose(`dose.${at + 60_000}.b`, at + 60_000, [B])],
    keepAll,
    valid,
  );
  expect(os.size).toBe(0);
});

test("reminders show while the app is open (H6)", () => {
  showRemindersInForeground();
  expect(Notifications.setNotificationHandler).toHaveBeenCalledTimes(1);
});
