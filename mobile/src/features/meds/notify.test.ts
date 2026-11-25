import * as Notifications from "expo-notifications";
import { Platform } from "react-native";
import { showRemindersInForeground } from "@/lib/notifications";

import {
  alarmClocksFor,
  CHANNEL_ALARM,
  CHANNEL_SILENT,
  cancelSnoozeOf,
  defaultMedAlarm,
  dismissDoseCopies,
  dismissRecordedReminders,
  doseSound,
  exactAlarmState,
  medAlarmChoices,
  medAlarmOn,
  registerReminderKinds,
  rememberExactAlarm,
  rememberSound,
  resetRegisteredKinds,
  ringsFor,
  setAlarmSound,
  setMedAlarm,
  snooze,
  snoozeAlarms,
  soundChanged,
  syncReminders,
} from "./notify";
import type { PlannedNotification } from "./reminders";

type Scheduled = {
  identifier: string;
  content: { body?: string; data?: unknown };
  trigger: { date: number };
};
// the encrypted local store needs a session: an in-memory one here (shared across modules)
const mockStored = new Map<string, boolean | string>();
// the Android alarm clock (Q79): a fake whose availability the tests set
const mockAlarm = { available: false, cancel: jest.fn(), add: jest.fn() };
jest.mock("../../../modules/dose-alarm", () => ({
  alarmClockAvailable: () => mockAlarm.available,
  cancelAlarmClock: (id: string) => mockAlarm.cancel(id),
  addAlarmClock: (id: string, at: number) => mockAlarm.add(id, at),
}));
jest.mock("@/lib/local-store", () => ({
  localStore: async () => ({
    getBoolean: (k: string) => mockStored.get(k) as boolean | undefined,
    getString: (k: string) => mockStored.get(k) as string | undefined,
    set: (k: string, v: boolean | string) => mockStored.set(k, v),
  }),
}));

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

test("the soonest reminders are set first, and nothing is cancelled before they are", async () => {
  const was = Platform.OS;
  Platform.OS = "android"; // Android: new ones first (iOS has its own order)
  const schedule = jest.mocked(Notifications.scheduleNotificationAsync).getMockImplementation();
  const cancel = jest
    .mocked(Notifications.cancelScheduledNotificationAsync)
    .getMockImplementation();
  try {
    const at = Date.now() + 3_600_000;
    os.set(`dose.${at + 1}.old`, {
      identifier: `dose.${at + 1}.old`,
      content: {},
      trigger: { date: at + 1 },
    });
    const order: string[] = [];
    const cancel = jest
      .mocked(Notifications.cancelScheduledNotificationAsync)
      .getMockImplementation();
    jest.mocked(Notifications.scheduleNotificationAsync).mockImplementation(async (r) => {
      order.push(`+${r.identifier ?? ""}`);
      os.set(r.identifier ?? "", {
        identifier: r.identifier ?? "",
        content: {},
        trigger: { date: 0 },
      });
      return r.identifier ?? "";
    });
    jest.mocked(Notifications.cancelScheduledNotificationAsync).mockImplementation(async (id) => {
      order.push(`-${id}`);
      os.delete(id);
    });
    const later = dose(`dose.${at + 7_200_000}.l`, at + 7_200_000, [B]);
    await syncReminders([later, dose(`dose.${at}.s`, at, [A])], keepAll, always);
    expect(order).toEqual([`+dose.${at}.s`, `+dose.${at + 7_200_000}.l`, `-dose.${at + 1}.old`]);
    jest.mocked(Notifications.cancelScheduledNotificationAsync).mockImplementation(cancel);
  } finally {
    Platform.OS = was;
    jest.mocked(Notifications.scheduleNotificationAsync).mockImplementation(schedule);
    jest.mocked(Notifications.cancelScheduledNotificationAsync).mockImplementation(cancel);
  }
});

test("iOS: the old ones go first, never more than 64 pending (medical review H-1)", async () => {
  const was = Platform.OS;
  Platform.OS = "ios";
  try {
    const base = Date.now() + 3_600_000;
    for (let k = 0; k < 56; k += 1) {
      const id = `dose.${base + k * 60_000}.old`;
      os.set(id, { identifier: id, content: {}, trigger: { date: base + k * 60_000 } });
    }
    let most = 0;
    const schedule = jest.mocked(Notifications.scheduleNotificationAsync).getMockImplementation();
    jest.mocked(Notifications.scheduleNotificationAsync).mockImplementation(async (r) => {
      const id = await (schedule as NonNullable<typeof schedule>)(r);
      most = Math.max(most, os.size);
      return id;
    });
    const planned = Array.from({ length: 56 }, (_, k) =>
      dose(`dose.${base + k * 60_000}.new`, base + k * 60_000, [A]),
    );
    await syncReminders(planned, keepAll, always);
    jest.mocked(Notifications.scheduleNotificationAsync).mockImplementation(schedule);
    expect(most).toBeLessThanOrEqual(64);
    expect([...os.keys()].every((id) => id.endsWith(".new"))).toBe(true);
    expect(os.size).toBe(56);
  } finally {
    Platform.OS = was;
  }
});

test("a future minute whose content changed is never pending twice past its batch (M-1)", async () => {
  const was = Platform.OS;
  Platform.OS = "android"; // Android: new ones first (iOS has its own order)
  const schedule = jest.mocked(Notifications.scheduleNotificationAsync).getMockImplementation();
  const cancel = jest
    .mocked(Notifications.cancelScheduledNotificationAsync)
    .getMockImplementation();
  try {
    const at = Date.now() + 3_600_000;
    const far = at + 86_400_000;
    os.set(`dose.${at}.ab`, { identifier: `dose.${at}.ab`, content: {}, trigger: { date: at } });
    os.set(`dose.${far}.x`, { identifier: `dose.${far}.x`, content: {}, trigger: { date: far } });
    const order: string[] = [];
    const cancel = jest
      .mocked(Notifications.cancelScheduledNotificationAsync)
      .getMockImplementation();
    jest.mocked(Notifications.scheduleNotificationAsync).mockImplementation(async (r) => {
      order.push(`+${r.identifier ?? ""}`);
      return (schedule as NonNullable<typeof schedule>)(r);
    });
    jest.mocked(Notifications.cancelScheduledNotificationAsync).mockImplementation(async (id) => {
      order.push(`-${id}`);
      return (cancel as NonNullable<typeof cancel>)(id);
    });
    // A was recorded early: only B is left of that minute
    await syncReminders([dose(`dose.${at}.b`, at, [B])], keepAll, always);
    expect(order).toEqual([`+dose.${at}.b`, `-dose.${at}.ab`, `-dose.${far}.x`]);
  } finally {
    Platform.OS = was;
    jest.mocked(Notifications.scheduleNotificationAsync).mockImplementation(schedule);
    jest.mocked(Notifications.cancelScheduledNotificationAsync).mockImplementation(cancel);
  }
});

test("one refused reminder does not stop the others (M-2)", async () => {
  const at = Date.now() + 3_600_000;
  const schedule = jest.mocked(Notifications.scheduleNotificationAsync).getMockImplementation();
  jest.mocked(Notifications.scheduleNotificationAsync).mockImplementation(async (r) => {
    if (r.identifier === `dose.${at}.bad`) throw new Error("refused");
    return (schedule as NonNullable<typeof schedule>)(r);
  });
  const later = Array.from({ length: 8 }, (_, k) =>
    dose(`dose.${at + (k + 1) * 60_000}.ok`, at + (k + 1) * 60_000, [A]),
  );
  await syncReminders([dose(`dose.${at}.bad`, at, [B]), ...later], keepAll, always);
  jest.mocked(Notifications.scheduleNotificationAsync).mockImplementation(schedule);
  expect(os.size).toBe(8);
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

test("reminders of a kind whose list is not loaded are kept (security review 2.6c M3)", async () => {
  const at = Date.now() + 3_600_000;
  os.set(`appt.${at}.x`, { identifier: `appt.${at}.x`, content: {}, trigger: { date: at } });
  os.set(`dose.${at}.y`, { identifier: `dose.${at}.y`, content: {}, trigger: { date: at } });
  await syncReminders([], keepAll, always, (id) => id.startsWith("appt."));
  expect(os.has(`appt.${at}.x`)).toBe(true);
  expect(os.has(`dose.${at}.y`)).toBe(false);
});

test("H18: after the exact-alarm permission changes, every planned reminder is set anew", async () => {
  const at = Date.now() + 3_600_000;
  const due = Date.now() - 60_000;
  const planned = [dose(`dose.${at}.a`, at, [A]), dose(`dose.${due}.b`, due, [B], true)];
  os.set(`dose.${due}.b`, {
    identifier: `dose.${due}.b`,
    content: { data: planned[1].data },
    trigger: { date: due },
  });
  await syncReminders(planned, keepAll, always);
  jest.clearAllMocks();
  await syncReminders(planned, keepAll, always, () => false, true);
  // the coming one is scheduled again (now as the OS allows); the late one fires at once -
  // Android drops exact alarms when the permission is taken away. Set again in place under
  // the same id (it replaces the alarm), never cancelled first (MIUI: seconds per call)
  expect(Notifications.cancelScheduledNotificationAsync).not.toHaveBeenCalled();
  expect(Notifications.scheduleNotificationAsync).toHaveBeenCalledTimes(2);
  expect(os.get(`dose.${due}.b`)?.trigger.date).toBeGreaterThan(Date.now() - 1000);
  expect(os.has(`dose.${at}.a`)).toBe(true);
  expect(os.has(`dose.${due}.b`)).toBe(true);
});

test("H18: reminders are renewed after a permission change and once per app start (Android)", async () => {
  const was = Platform.OS;
  Platform.OS = "android";
  const perm = Notifications.getExactAlarmPermissionsAsync as jest.Mock;
  perm.mockResolvedValue({ granted: true, status: "granted" });
  try {
    expect(await exactAlarmState()).toEqual({ granted: true, changed: true });
    await rememberExactAlarm(true);
    expect(await exactAlarmState()).toEqual({ granted: true, changed: false });
    // taken away while the app runs
    perm.mockResolvedValueOnce({ granted: false, status: "denied" });
    expect(await exactAlarmState()).toEqual({ granted: false, changed: true });
    // taken away and given back while the app was stopped: the remembered state reads the
    // same, yet Android dropped the exact alarms - a new app process renews once
    let fresh: typeof exactAlarmState = exactAlarmState;
    jest.isolateModules(() => {
      fresh = (require("./notify") as typeof import("./notify")).exactAlarmState;
    });
    expect(await fresh()).toEqual({ granted: true, changed: true });
  } finally {
    Platform.OS = was;
  }
});

test("'Уусан' cancels the dose's repeat and its snoozes (user 2026.11.19)", async () => {
  for (const id of ["again.dose.1.a", "snooze.dose.1.a", "snooze.again.dose.1.a"]) {
    os.set(id, { identifier: id, content: {}, trigger: { date: 1 } });
  }
  await cancelSnoozeOf("again.dose.1.a");
  expect(os.size).toBe(0);
});

test("a new sound renews every reminder once: loud by default, quiet when turned off", async () => {
  mockStored.clear();
  expect(await soundChanged()).toBe(true); // set before the loud channel existed
  await rememberSound();
  expect(await soundChanged()).toBe(false);
  await setAlarmSound(false);
  expect(await soundChanged()).toBe(true);
  await rememberSound();
  expect(await soundChanged()).toBe(false);
});

test("'Уусан' takes every copy of that dose time out of the tray (medical review M2)", async () => {
  await dismissDoseCopies("again.dose.1.a");
  const dismissed = jest
    .mocked(Notifications.dismissNotificationAsync)
    .mock.calls.map(([id]) => id)
    .sort();
  expect(dismissed).toEqual(
    ["again.dose.1.a", "dose.1.a", "snooze.again.dose.1.a", "snooze.dose.1.a"].sort(),
  );
});

const texts = {
  channel: "Эмийн сануулга",
  channelAlarm: "Эмийн сануулга (чанга)",
  channelSilent: "Эмийн сануулга (сэрүүлэг дуугарах үед)",
  taken: "Уусан",
  takenAll: "Бүгдийг уусан",
  snooze: "10 мин дараа",
  placeholder: "Эм уух цаг боллоо",
};

test("H6: channels and categories are registered once per app process, again for a new language", async () => {
  resetRegisteredKinds();
  await registerReminderKinds(texts);
  await registerReminderKinds(texts);
  // each is a slow OS round trip on some phones (MIUI): a sync never waits on them again
  expect(Notifications.setNotificationCategoryAsync).toHaveBeenCalledTimes(2);
  await registerReminderKinds({ ...texts, taken: "Taken" });
  expect(Notifications.setNotificationCategoryAsync).toHaveBeenCalledTimes(4);
});

test("H6: a failed registration is tried again by the next sync", async () => {
  resetRegisteredKinds();
  (Notifications.setNotificationCategoryAsync as jest.Mock).mockRejectedValueOnce(new Error("os"));
  await expect(registerReminderKinds(texts)).rejects.toThrow("os");
  await registerReminderKinds(texts);
  expect(Notifications.setNotificationCategoryAsync).toHaveBeenCalledTimes(3);
});

test("H40: a reminder in the tray goes once every dose it lists is recorded, not before", async () => {
  const at = 1_795_573_200_000; // a whole minute
  const shownReq = (identifier: string, d: string[]) => ({
    request: {
      identifier,
      content: { data: { kind: "dose", p: P, d: d.map((m) => ({ m, at })) } },
    },
  });
  (Notifications.getPresentedNotificationsAsync as jest.Mock).mockResolvedValueOnce([
    shownReq(`dose.${at}.one`, [A]),
    shownReq(`again.dose.${at}.both`, [A, B]),
    shownReq("appt.1.x", [A]), // not a dose reminder
    // a malformed item beside a recorded one: never counted as recorded
    {
      request: {
        identifier: `dose.${at}.bad`,
        content: {
          data: {
            kind: "dose",
            p: P,
            d: [
              { m: A, at },
              { m: "x", at },
            ],
          },
        },
      },
    },
  ]);
  await dismissRecordedReminders(new Set([`${A}@${at}`]));
  expect(Notifications.dismissNotificationAsync).toHaveBeenCalledTimes(1);
  expect(Notifications.dismissNotificationAsync).toHaveBeenCalledWith(`dose.${at}.one`);
});

test("Q79: on Android with exact alarms the alarm clock rings and the reminder itself is silent", async () => {
  const was = Platform.OS;
  Platform.OS = "android";
  try {
    await setAlarmSound(true);
    mockAlarm.available = true;
    expect(await doseSound()).toMatchObject({
      channel: CHANNEL_SILENT,
      fallback: CHANNEL_ALARM,
      alarmClock: true,
    });
    // without the permission (H18) the loud channel stays, no alarm clock
    mockAlarm.available = false;
    expect(await doseSound()).toMatchObject({ channel: CHANNEL_ALARM, alarmClock: false });
    // the quiet setting: neither
    await setAlarmSound(false);
    mockAlarm.available = true;
    expect(await doseSound()).toMatchObject({ channel: "doses", alarmClock: false });
  } finally {
    Platform.OS = was;
    mockAlarm.available = false;
    await setAlarmSound(true);
  }
});

test("Q79: iOS never uses the alarm clock", async () => {
  const was = Platform.OS;
  Platform.OS = "ios";
  try {
    mockAlarm.available = true;
    expect((await doseSound()).alarmClock).toBe(false);
  } finally {
    Platform.OS = was;
    mockAlarm.available = false;
  }
});

test("Q79: the alarm clock rings doses and repeats still to come - never a late one or a renew notice", () => {
  const now = Date.now();
  const soon = now + 600_000;
  const planned = [
    dose(`dose.${soon}.a`, soon, [A]),
    { ...dose(`again.dose.${soon}.a`, soon + 900_000, [A]), id: `again.dose.${soon}.a` },
    dose(`dose.${now - 60_000}.b`, now - 60_000, [B], true),
    {
      id: `renew.${soon}.x`,
      at: soon,
      title: "renew",
      body: "",
      kind: "renew" as const,
      data: { kind: "renew" as const, p: P, d: [] },
      due: false,
    },
  ];
  expect(alarmClocksFor(planned, now)).toEqual([
    { id: `dose.${soon}.a`, at: soon },
    { id: `again.dose.${soon}.a`, at: soon + 900_000 },
  ]);
});

test("Q79: a recorded dose cancels its alarm clock and its repeat's at once", async () => {
  mockAlarm.cancel.mockClear();
  await cancelSnoozeOf("snooze.again.dose.1795573200000.abc");
  expect(mockAlarm.cancel.mock.calls.map(([id]) => id)).toEqual([
    "dose.1795573200000.abc",
    "again.dose.1795573200000.abc",
    "snooze.dose.1795573200000.abc",
    "snooze.again.dose.1795573200000.abc",
  ]);
});

test("Q79: '10 мин дараа' rings by the alarm clock too, and is kept on the next sync while still set", async () => {
  const was = Platform.OS;
  Platform.OS = "android";
  try {
    await setAlarmSound(true);
    mockAlarm.available = true;
    mockAlarm.add.mockClear();
    const at = Date.now() - 60_000;
    await snooze(
      `dose.${at}.a`,
      {
        title: "t",
        body: "1 тун",
        data: { kind: "dose", p: P, d: [{ m: A, at: Math.floor(at / 60_000) * 60_000 }] },
      },
      always,
    );
    const set = os.get(`snooze.dose.${at}.a`) as unknown as {
      trigger: { channelId: string; date: number };
    };
    expect(set.trigger.channelId).toBe(CHANNEL_SILENT); // the alarm clock rings, not the notification
    expect(mockAlarm.add).toHaveBeenCalledWith(`snooze.dose.${at}.a`, set.trigger.date);
    const now = Date.now();
    expect(await snoozeAlarms(now, new Set([`snooze.dose.${at}.a`]))).toEqual([
      { id: `snooze.dose.${at}.a`, at: set.trigger.date },
    ]);
    // the OS no longer has it (the dose was recorded): forgotten
    expect(await snoozeAlarms(now, new Set())).toEqual([]);
    expect(await snoozeAlarms(now, new Set([`snooze.dose.${at}.a`]))).toEqual([]);
  } finally {
    Platform.OS = was;
    mockAlarm.available = false;
  }
});

test("Q79: without the alarm clock '10 мин дараа' uses the loud channel", async () => {
  const was = Platform.OS;
  Platform.OS = "android";
  try {
    await setAlarmSound(true);
    mockAlarm.available = false;
    mockAlarm.add.mockClear();
    const at = Date.now() - 60_000;
    await snooze(
      `dose.${at}.b`,
      {
        title: "t",
        body: "1 тун",
        data: { kind: "dose", p: P, d: [{ m: B, at: Math.floor(at / 60_000) * 60_000 }] },
      },
      always,
    );
    const set = os.get(`snooze.dose.${at}.b`) as unknown as { trigger: { channelId: string } };
    expect(set.trigger.channelId).toBe(CHANNEL_ALARM);
    expect(mockAlarm.add).not.toHaveBeenCalled();
  } finally {
    Platform.OS = was;
  }
});

test("Q79/H-1: a late reminder shown at once is loud - no alarm clock rings for it", async () => {
  const was = Platform.OS;
  Platform.OS = "android";
  try {
    await setAlarmSound(true);
    mockAlarm.available = true;
    const late = Math.floor((Date.now() - 120_000) / 60_000) * 60_000;
    // an alarm still pending after its time (held back), renewed: shown at once
    await Notifications.scheduleNotificationAsync({
      identifier: `dose.${late}.late`,
      content: { title: "t", body: "1 тун" },
      trigger: { type: Notifications.SchedulableTriggerInputTypes.DATE, date: late },
    });
    await syncReminders(
      [dose(`dose.${late}.late`, late, [A], true)],
      keepAll,
      always,
      () => false,
      true,
    );
    const set = os.get(`dose.${late}.late`) as unknown as { trigger: { channelId: string } };
    expect(set.trigger.channelId).toBe(CHANNEL_ALARM);
  } finally {
    Platform.OS = was;
    mockAlarm.available = false;
  }
});

test("Q79-3: immunosuppressants, corticosteroids and medicines of no known kind ring by default", async () => {
  expect(defaultMedAlarm("immunosuppressant")).toBe(true);
  expect(defaultMedAlarm("corticosteroid")).toBe(true);
  expect(defaultMedAlarm(null)).toBe(true); // typed in, "unknown": the safe side
  expect(defaultMedAlarm("antiviral")).toBe(false);
  expect(defaultMedAlarm("antihypertensive")).toBe(false);
  // the user's choice on this phone wins either way
  await setMedAlarm(A, false);
  await setMedAlarm(B, true);
  const choices = await medAlarmChoices();
  expect(medAlarmOn({ id: A, category: "immunosuppressant" }, choices)).toBe(false);
  expect(medAlarmOn({ id: B, category: "antiviral" }, choices)).toBe(true);
  mockStored.delete("prefs.med_alarm.v1");
});

test("Q79-3: a reminder rings by the alarm clock when a dose it lists does; the rest stay loud", async () => {
  const was = Platform.OS;
  Platform.OS = "android";
  try {
    await setAlarmSound(true);
    mockAlarm.available = true;
    const at = Date.now() + 3_600_000;
    const rings = ringsFor(new Set([A]));
    const planned = [
      dose(`dose.${at}.a`, at, [A]),
      dose(`dose.${at + 60_000}.b`, at + 60_000, [B]),
      dose(`dose.${at + 120_000}.ab`, at + 120_000, [A, B]),
    ];
    await syncReminders(planned, keepAll, always, () => false, false, rings);
    const channel = (id: string) =>
      (os.get(id) as unknown as { trigger: { channelId: string } }).trigger.channelId;
    expect(channel(`dose.${at}.a`)).toBe(CHANNEL_SILENT);
    expect(channel(`dose.${at + 60_000}.b`)).toBe(CHANNEL_ALARM);
    expect(channel(`dose.${at + 120_000}.ab`)).toBe(CHANNEL_SILENT);
    expect(alarmClocksFor(planned, Date.now(), rings).map((x) => x.id)).toEqual([
      `dose.${at}.a`,
      `dose.${at + 120_000}.ab`,
    ]);
  } finally {
    Platform.OS = was;
    mockAlarm.available = false;
  }
});

test("Q79-3: '10 мин дараа' of a medicine not ringing like an alarm sets no alarm clock", async () => {
  const was = Platform.OS;
  Platform.OS = "android";
  try {
    await setAlarmSound(true);
    mockAlarm.available = true;
    const at = Date.now() - 60_000;
    await snooze(
      `dose.${at}.c`,
      {
        title: "t",
        body: "1 тун",
        data: { kind: "dose", p: P, d: [{ m: B, at: Math.floor(at / 60_000) * 60_000 }] },
      },
      always,
      false,
    );
    const set = os.get(`snooze.dose.${at}.c`) as unknown as { trigger: { channelId: string } };
    expect(set.trigger.channelId).toBe(CHANNEL_ALARM);
    expect(mockAlarm.add).not.toHaveBeenCalled();
  } finally {
    Platform.OS = was;
    mockAlarm.available = false;
  }
});

test("Q79-3: turning a medicine's alarm on or off sets the reminders anew; a new medicine does not", async () => {
  const was = Platform.OS;
  Platform.OS = "android";
  try {
    await setAlarmSound(true);
    mockAlarm.available = true;
    await rememberSound({ [A]: true });
    expect(await soundChanged({ [A]: true })).toBe(false);
    expect(await soundChanged({ [A]: true, [B]: false })).toBe(false); // B is new: set as it is
    // remembered after that sync: B turned on later is set anew (medical review H-1)
    await rememberSound({ [A]: true, [B]: false });
    expect(await soundChanged({ [A]: true, [B]: true })).toBe(true);
    expect(await soundChanged({ [A]: false })).toBe(true);
    // a value from before Q79-3 (the channel alone): set anew once
    mockStored.set("reminders.channel.v1", CHANNEL_SILENT);
    expect(await soundChanged({ [A]: true })).toBe(true);
  } finally {
    Platform.OS = was;
    mockAlarm.available = false;
    mockStored.delete("reminders.channel.v1");
  }
});
