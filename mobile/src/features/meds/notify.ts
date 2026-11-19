import * as Notifications from "expo-notifications";
import { Platform } from "react-native";
import type { PlannedAppointmentReminder } from "@/features/health/appointment-reminders";
import { localStore } from "@/lib/local-store";

import type { DoseItem, PlannedNotification } from "./reminders";

/**
 * Local dose reminders on the OS (expo-notifications, SDK 58): one Android channel with a
 * private lock-screen view (H10), two categories with "Уусан" / "Бүгдийг уусан" and
 * "10 мин дараа", and a sync that keeps the OS schedule equal to the plan.
 */

export const CHANNEL = "doses";
/** Loud: the alarm stream (sounds in silent mode), a long sound and vibration - the user's
 * choice 2026.11.19 after a real phone: the short default sound without vibration went
 * unnoticed. Channels are fixed once made: the quiet one stays for whoever turns this off. */
export const CHANNEL_ALARM = "doses-alarm";
export const ALARM_SOUND = "dose_alarm.wav";
export const CATEGORY_ONE = "dose_one";
export const CATEGORY_MANY = "dose_many";
export const ACTION_TAKEN = "taken";
export const ACTION_SNOOZE = "snooze";
export const SNOOZE_MS = 10 * 60_000;

const OURS = /^(dose|renew|snooze|appt|again)\./;
const NAMES_KEY = "prefs.reminder_names.v1";

export type NotifyTexts = {
  channel: string;
  channelAlarm: string;
  taken: string;
  takenAll: string;
  snooze: string;
  placeholder: string; // iOS: shown instead of the text when previews are hidden
};

/** Whether the user chose to show medicine names in reminders (off by default - H10). */
export async function showNames(): Promise<boolean> {
  return (await localStore()).getBoolean(NAMES_KEY) ?? false;
}

const DETAILS_KEY = "prefs.appointment_details.v1";

/** Whether appointment reminders show the title and place (off by default - H10). */
export async function showAppointmentDetails(): Promise<boolean> {
  return (await localStore()).getBoolean(DETAILS_KEY) ?? false;
}

export async function setShowAppointmentDetails(on: boolean): Promise<void> {
  (await localStore()).set(DETAILS_KEY, on);
}

export async function setShowNames(on: boolean): Promise<void> {
  (await localStore()).set(NAMES_KEY, on);
}

const ALARM_KEY = "prefs.reminder_alarm.v1";

/** Whether dose reminders ring like an alarm (on by default). */
export async function alarmSound(): Promise<boolean> {
  return (await localStore()).getBoolean(ALARM_KEY) ?? true;
}

export async function setAlarmSound(on: boolean): Promise<void> {
  (await localStore()).set(ALARM_KEY, on);
}

const CHANNEL_KEY = "reminders.channel.v1";

/** Whether the reminders already on the phone were set on another channel or sound (the
 * setting changed, or an update brought the loud one): then they are all set anew. */
export async function soundChanged(): Promise<boolean> {
  const { channel } = await doseSound();
  const before = (await localStore()).getString(CHANNEL_KEY);
  return (before ?? CHANNEL) !== channel;
}

export async function rememberSound(): Promise<void> {
  const { channel } = await doseSound();
  (await localStore()).set(CHANNEL_KEY, channel);
}

/** The channel (Android) and sound (iOS) dose reminders use now. */
export async function doseSound(): Promise<{ channel: string; sound: string | true }> {
  const loud = await alarmSound().catch(() => true);
  return loud ? { channel: CHANNEL_ALARM, sound: ALARM_SOUND } : { channel: CHANNEL, sound: true };
}

/** Channel and categories, in the app's language (re-registered on each sync). */
export async function registerReminderKinds(texts: NotifyTexts): Promise<void> {
  if (Platform.OS === "android") {
    await Notifications.setNotificationChannelAsync(CHANNEL, {
      name: texts.channel,
      importance: Notifications.AndroidImportance.HIGH,
      // the secure lock screen shows "content hidden", never the text
      lockscreenVisibility: Notifications.AndroidNotificationVisibility.PRIVATE,
    });
    await Notifications.setNotificationChannelAsync(CHANNEL_ALARM, {
      name: texts.channelAlarm,
      importance: Notifications.AndroidImportance.MAX,
      lockscreenVisibility: Notifications.AndroidNotificationVisibility.PRIVATE,
      sound: ALARM_SOUND,
      audioAttributes: {
        usage: Notifications.AndroidAudioUsage.ALARM,
        contentType: Notifications.AndroidAudioContentType.SONIFICATION,
      },
      enableVibrate: true,
      vibrationPattern: [0, 700, 300, 700, 300, 700],
      bypassDnd: false,
    });
  }
  // "Уусан" opens the app, which records the dose at once (whether a background action runs
  // with the app closed is checked on real phones - docs/08)
  const snooze = {
    identifier: ACTION_SNOOZE,
    buttonTitle: texts.snooze,
    options: { opensAppToForeground: true },
  };
  const options = { previewPlaceholder: texts.placeholder };
  await Notifications.setNotificationCategoryAsync(
    CATEGORY_ONE,
    [
      {
        identifier: ACTION_TAKEN,
        buttonTitle: texts.taken,
        options: { opensAppToForeground: true },
      },
      snooze,
    ],
    options,
  );
  await Notifications.setNotificationCategoryAsync(
    CATEGORY_MANY,
    [
      {
        identifier: ACTION_TAKEN,
        buttonTitle: texts.takenAll,
        options: { opensAppToForeground: true },
      },
      snooze,
    ],
    options,
  );
}

/** Everything this phone schedules: dose reminders, the renew notice, appointments (2.6c). */
export type Planned = PlannedNotification | PlannedAppointmentReminder;

function content(
  n: Pick<Planned, "title" | "body" | "data" | "kind">,
  sound: string | true = true,
) {
  return {
    title: n.title,
    body: n.body,
    data: n.data,
    // iOS: a bundled file for doses when ringing like an alarm, else the default; Android
    // takes the sound from the channel
    sound: n.kind === "dose" ? sound : true,
    ...(n.kind === "dose" && "d" in n.data
      ? { categoryIdentifier: n.data.d.length > 1 ? CATEGORY_MANY : CATEGORY_ONE }
      : {}),
  };
}

/**
 * Make the OS schedule equal to `planned`: ours not planned any more are cancelled, new ones
 * scheduled; unchanged ones are left (same id = same time and content), and one already due
 * (a late alarm) is kept but never scheduled anew. A "10 мин дараа" stays only while every
 * dose it lists is still planned and unrecorded (`keepSnooze`). New ones go first, soonest
 * first, a few calls at a time; cancelling what is no longer planned comes last. `valid()` is
 * checked between batches: a sign-out meanwhile stops the sync, and anything it scheduled is
 * removed.
 */
export async function syncReminders(
  planned: readonly Planned[],
  keepSnooze: (items: DoseItem[], body: string) => boolean,
  valid: () => boolean,
  /** an identifier not planned now but kept (its kind's data is not loaded) */
  keepUnplanned: (id: string) => boolean = () => false,
  /** schedule every reminder still to come anew (the exact-alarm permission changed: the
   * OS keeps an alarm as exact or inexact as it was set - H18) */
  renewAll = false,
): Promise<void> {
  const existing = await Notifications.getAllScheduledNotificationsAsync();
  const { channel, sound } = await doseSound();
  if (!valid()) return;
  const wanted = new Map(planned.map((n) => [n.id, n]));
  const scheduled: string[] = [];
  const stop = () =>
    inBatches(scheduled, (id) => Notifications.cancelScheduledNotificationAsync(id));
  // minutes of late alarms (still pending after their time) cancelled for a new content
  const lateReplaced = new Set<number>();
  const renewed = new Set<string>();
  const lateObsolete: string[] = [];
  const obsolete: string[] = [];
  const now = Date.now();
  for (const n of existing) {
    if (!OURS.test(n.identifier)) continue;
    const keep = n.identifier.startsWith("snooze.")
      ? keepSnooze(doseData(n.content.data)?.d ?? [], n.content.body ?? "")
      : wanted.has(n.identifier) || keepUnplanned(n.identifier);
    const plan = wanted.get(n.identifier);
    // renewed: a planned one is set again under the new permission. A due one fires at once:
    // Android drops exact alarms when the permission is taken away (and on a force stop), and
    // a held-back inexact one is late already (H18). Scheduled again under the same id, which
    // replaces the OS alarm - no cancel first: on MIUI each call can take 2-22 s, and cancelling
    // ~45 reminders before setting any left no reminder for minutes (real phone, 2026.11.19)
    if (renewAll && keep && plan !== undefined) {
      renewed.add(n.identifier);
      if (plan.due) lateReplaced.add(plan.at);
      continue;
    }
    if (keep) continue;
    const at = Number(n.identifier.match(/^dose\.(\d+)\./)?.[1]);
    if (Number.isFinite(at) && at <= now) {
      lateReplaced.add(at);
      lateObsolete.push(n.identifier);
    } else obsolete.push(n.identifier);
  }
  const cancel = (id: string) => Notifications.cancelScheduledNotificationAsync(id);
  // a late alarm whose content changed goes before its replacement (never both shown)
  await inBatches(lateObsolete, cancel);
  if (!valid()) return;
  // iOS keeps only the 64 soonest pending: no room to set the new ones first, or later days and
  // the "renew" notice would be dropped (medical review H-1). Its calls are quick anyway.
  let rest = obsolete;
  if (Platform.OS === "ios") {
    await inBatches(obsolete, cancel);
    rest = [];
    if (!valid()) return;
  }
  // a future minute whose content changed (a dose changed, one of a shared minute recorded
  // early): its old reminder goes as soon as the new one is set - never two lists for one dose
  // time (medical review M-1)
  const oldOfMinute = new Map<number, string[]>();
  for (const id of rest) {
    const at = Number(id.match(/^dose\.(\d+)\./)?.[1]);
    if (Number.isFinite(at)) oldOfMinute.set(at, [...(oldOfMinute.get(at) ?? []), id]);
  }
  const leftover = new Set(rest);
  const have = new Set(existing.map((n) => n.identifier).filter((id) => !renewed.has(id)));
  // the soonest first: the next dose is reminded again before the rest of the week is set
  const toSchedule = planned
    .filter((n) => !have.has(n.id))
    // a due one is scheduled only to replace a late alarm whose content changed (one dose of
    // a shared minute recorded meanwhile): the rest of that minute is still reminded, now
    .filter((n) => !n.due || lateReplaced.has(n.at))
    .sort((a, b) => a.at - b.at);
  for (let i = 0; i < toSchedule.length; i += BATCH) {
    if (!valid()) return stop();
    const batch = toSchedule.slice(i, i + BATCH);
    // one refused call does not stop the rest; what was set is known (a sign-out removes it -
    // medical review M-2); a failed one is tried again by the next sync
    const results = await Promise.allSettled(
      batch.map((n) =>
        Notifications.scheduleNotificationAsync({
          identifier: n.id,
          content: content(n, sound),
          trigger: {
            type: Notifications.SchedulableTriggerInputTypes.DATE,
            date: n.due ? now + 2_000 : n.at,
            channelId: n.kind === "dose" ? channel : CHANNEL,
          },
        }),
      ),
    );
    const set = batch.filter((_, k) => results[k]?.status === "fulfilled");
    scheduled.push(...set.map((n) => n.id));
    const replaced = set.flatMap((n) => oldOfMinute.get(n.at) ?? []);
    await inBatches(replaced, cancel);
    for (const id of replaced) leftover.delete(id);
  }
  if (!valid()) return stop();
  // the rest of what is no longer planned goes last: a reminder too many for a moment, never
  // one too few
  await inBatches([...leftover], cancel);
  if (!valid()) await stop();
}

/** OS calls a few at a time: each waits on the system (seconds on some phones), not on us. */
const BATCH = 6;

async function inBatches(ids: readonly string[], call: (id: string) => Promise<unknown>) {
  for (let i = 0; i < ids.length; i += BATCH) {
    await Promise.allSettled(ids.slice(i, i + BATCH).map(call));
  }
}

/** "10 мин дараа": the same reminder once more, ten minutes from now. */
export async function snooze(
  identifier: string,
  shown: { title: string; body: string; data: unknown },
  valid: () => boolean,
): Promise<void> {
  const data = doseData(shown.data);
  if (!data || !valid()) return;
  const id = `snooze.${identifier.replace(/^snooze\./, "")}`;
  const { channel, sound } = await doseSound();
  await Notifications.scheduleNotificationAsync({
    identifier: id,
    content: content({ title: shown.title, body: shown.body, data, kind: "dose" }, sound),
    trigger: {
      type: Notifications.SchedulableTriggerInputTypes.DATE,
      date: Date.now() + SNOOZE_MS,
      channelId: channel,
    },
  });
  if (!valid()) await Notifications.cancelScheduledNotificationAsync(id); // signed out meanwhile
}

/** This phone's own local dose reminders (a push message can never look like one). */
export const LOCAL_DOSE_ID = /^(snooze\.)?(again\.)?dose\.\d+\.[0-9a-z]+$/;

const copiesOf = (identifier: string) => {
  const base = identifier.replace(/^snooze[.]/, "").replace(/^again[.]/, "");
  return [base, `again.${base}`, `snooze.${base}`, `snooze.again.${base}`];
};

/** A recorded dose: every copy already shown (reminder, repeat, snoozes) leaves the tray. */
export async function dismissDoseCopies(identifier: string): Promise<void> {
  await Promise.allSettled(
    copiesOf(identifier).map((id) => Notifications.dismissNotificationAsync(id)),
  );
}

/** A recorded dose: its "10 мин дараа" copies and its 15-minute repeat are no longer wanted. */
export async function cancelSnoozeOf(identifier: string): Promise<void> {
  const base = identifier.replace(/^snooze\./, "").replace(/^again\./, "");
  await Promise.allSettled(
    [`snooze.${base}`, `snooze.again.${base}`, `again.${base}`].map((id) =>
      Notifications.cancelScheduledNotificationAsync(id),
    ),
  );
}

const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/;

/** The ids and instants a dose reminder carries - checked, never trusted blindly. */
export function doseData(raw: unknown): { kind: "dose"; p: string; d: DoseItem[] } | null {
  if (typeof raw !== "object" || raw === null) return null;
  const { kind, p, d } = raw as { kind?: unknown; p?: unknown; d?: unknown };
  if (kind !== "dose" || typeof p !== "string" || !UUID.test(p) || !Array.isArray(d)) return null;
  const items = d.filter(
    (x): x is DoseItem =>
      typeof x === "object" &&
      x !== null &&
      typeof (x as DoseItem).m === "string" &&
      UUID.test((x as DoseItem).m) &&
      Number.isInteger((x as DoseItem).at) &&
      (x as DoseItem).at % 60_000 === 0,
  );
  return items.length ? { kind, p, d: items } : null;
}

const EXACT_KEY = "reminders.exact_alarm.v1";
/** set anew once in this app process (see `exactAlarmState`) */
let renewedInProcess = false;

/**
 * Android: whether reminders must be set anew because the exact-alarm permission may not be
 * what it was when they were scheduled. Granted on the explanation screen while the app runs:
 * the remembered state (encrypted local store) differs. Taken away: Android stops the app and
 * drops its exact alarms - given back before the app starts again, the state reads the same,
 * so every app start renews once too (2.10d, emulator).
 */
export async function exactAlarmState(): Promise<{ granted: boolean; changed: boolean } | null> {
  if (Platform.OS !== "android") return null;
  let granted: boolean;
  try {
    granted = (await Notifications.getExactAlarmPermissionsAsync()).granted;
  } catch {
    return null;
  }
  const before = (await localStore()).getBoolean(EXACT_KEY);
  // never recorded: the reminders already on the phone may have been set without it
  const changed = before === undefined ? granted : before !== granted;
  return { granted, changed: changed || !renewedInProcess };
}

export async function rememberExactAlarm(granted: boolean): Promise<void> {
  (await localStore()).set(EXACT_KEY, granted);
  renewedInProcess = true;
}
