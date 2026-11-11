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
export const CATEGORY_ONE = "dose_one";
export const CATEGORY_MANY = "dose_many";
export const ACTION_TAKEN = "taken";
export const ACTION_SNOOZE = "snooze";
export const SNOOZE_MS = 10 * 60_000;

const OURS = /^(dose|renew|snooze|appt)\./;
const NAMES_KEY = "prefs.reminder_names.v1";

export type NotifyTexts = {
  channel: string;
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

/** Channel and categories, in the app's language (re-registered on each sync). */
export async function registerReminderKinds(texts: NotifyTexts): Promise<void> {
  if (Platform.OS === "android") {
    await Notifications.setNotificationChannelAsync(CHANNEL, {
      name: texts.channel,
      importance: Notifications.AndroidImportance.HIGH,
      // the secure lock screen shows "content hidden", never the text
      lockscreenVisibility: Notifications.AndroidNotificationVisibility.PRIVATE,
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

function content(n: Pick<Planned, "title" | "body" | "data" | "kind">) {
  return {
    title: n.title,
    body: n.body,
    data: n.data,
    sound: true, // the system default sound (a string names a bundled custom file)
    ...(n.kind === "dose" && "d" in n.data
      ? { categoryIdentifier: n.data.d.length > 1 ? CATEGORY_MANY : CATEGORY_ONE }
      : {}),
  };
}

/**
 * Make the OS schedule equal to `planned`: ours not planned any more are cancelled, new ones
 * scheduled; unchanged ones are left (same id = same time and content), and one already due
 * (a late alarm) is kept but never scheduled anew. A "10 мин дараа" stays only while every
 * dose it lists is still planned and unrecorded (`keepSnooze`). `valid()` is checked before
 * every OS call: a sign-out meanwhile stops the sync, and anything it scheduled is removed.
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
  const wanted = new Map(planned.map((n) => [n.id, n]));
  const scheduled: string[] = [];
  const stop = async () => {
    for (const id of scheduled) await Notifications.cancelScheduledNotificationAsync(id);
  };
  // minutes of late alarms (still pending after their time) cancelled for a new content
  const lateReplaced = new Set<number>();
  const renewed = new Set<string>();
  const now = Date.now();
  for (const n of existing) {
    if (!valid()) return stop();
    if (!OURS.test(n.identifier)) continue;
    const keep = n.identifier.startsWith("snooze.")
      ? keepSnooze(doseData(n.content.data)?.d ?? [], n.content.body ?? "")
      : wanted.has(n.identifier) || keepUnplanned(n.identifier);
    const plan = wanted.get(n.identifier);
    // renewed: a planned one is set again under the new permission. A due one fires at once:
    // Android drops exact alarms when the permission is taken away, and a held-back inexact
    // one is late already (H18)
    const renew = renewAll && keep && plan !== undefined;
    if (keep && !renew) continue;
    await Notifications.cancelScheduledNotificationAsync(n.identifier);
    if (renew) {
      renewed.add(n.identifier);
      if (plan.due) lateReplaced.add(plan.at);
      continue;
    }
    const at = Number(n.identifier.match(/^dose\.(\d+)\./)?.[1]);
    if (Number.isFinite(at) && at <= now) lateReplaced.add(at);
  }
  const have = new Set(existing.map((n) => n.identifier).filter((id) => !renewed.has(id)));
  for (const n of planned) {
    if (have.has(n.id)) continue;
    // a due one is scheduled only to replace a late alarm whose content changed (one dose of
    // a shared minute recorded meanwhile): the rest of that minute is still reminded, now
    if (n.due && !lateReplaced.has(n.at)) continue;
    if (!valid()) return stop();
    await Notifications.scheduleNotificationAsync({
      identifier: n.id,
      content: content(n),
      trigger: {
        type: Notifications.SchedulableTriggerInputTypes.DATE,
        date: n.due ? now + 2_000 : n.at,
        channelId: CHANNEL,
      },
    });
    scheduled.push(n.id);
  }
  if (!valid()) await stop();
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
  await Notifications.scheduleNotificationAsync({
    identifier: id,
    content: content({ title: shown.title, body: shown.body, data, kind: "dose" }),
    trigger: {
      type: Notifications.SchedulableTriggerInputTypes.DATE,
      date: Date.now() + SNOOZE_MS,
      channelId: CHANNEL,
    },
  });
  if (!valid()) await Notifications.cancelScheduledNotificationAsync(id); // signed out meanwhile
}

/** This phone's own local dose reminders (a push message can never look like one). */
export const LOCAL_DOSE_ID = /^(snooze\.)?dose\.\d+\.[0-9a-z]+$/;

/** A recorded dose: its "10 мин дараа" copy is no longer wanted. */
export async function cancelSnoozeOf(identifier: string): Promise<void> {
  await Notifications.cancelScheduledNotificationAsync(
    `snooze.${identifier.replace(/^snooze\./, "")}`,
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
