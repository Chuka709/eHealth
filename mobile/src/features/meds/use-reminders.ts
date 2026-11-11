import * as Notifications from "expo-notifications";
import { useRouter } from "expo-router";
import { useEffect, useRef } from "react";
import { Alert, AppState } from "react-native";
import { useTranslations } from "use-intl";
import { currentEpoch, isWiping } from "@/features/auth/session";
import { getStatus } from "@/features/auth/session-store";
import {
  appointmentData,
  LOCAL_APPOINTMENT_ID,
  planAppointmentReminders,
} from "@/features/health/appointment-reminders";
import {
  APPOINTMENTS,
  type Appointment,
  recordsKey,
  useRecords,
} from "@/features/health/use-health";
import { pushData, pushRoute } from "@/features/notices/push-route";
import { refreshNotices } from "@/features/notices/use-notifications";
import { setActiveProfile } from "@/features/records/active-profile";
import { ownProfile, type Patient, patientsKey, usePatients } from "@/features/records/use-profile";
import { formatDateTime } from "@/lib/dates";
import { queryClient } from "@/lib/query-client";
import {
  ACTION_SNOOZE,
  ACTION_TAKEN,
  cancelSnoozeOf,
  doseData,
  LOCAL_DOSE_ID,
  registerReminderKinds,
  showAppointmentDetails,
  showNames,
  snooze,
  syncReminders,
} from "./notify";
import { doseKey, doseStates, planOf } from "./plan";
import { onReminderSync } from "./reminder-bus";
import { planReminders, type ReminderMedicine } from "./reminders";
import { HOME_TIMEZONE } from "./slots";
import {
  type Medication,
  medicationsKey,
  recordDose,
  useIntakes,
  useMedications,
  useZones,
} from "./use-medications";
import { localDay, usePendingDoses } from "./use-today";
import { deviceZone } from "./use-zone-prompt";

export { requestReminderSync } from "./reminder-bus";

const DAY = 86_400_000;
const LOOK_AHEAD = 8 * DAY;

function unitOf(m: Medication, label: (unit: string) => string): string | null {
  const r = m.current_regimen ?? m.next_regimen;
  if (!r?.dose_unit) return null;
  return r.dose_unit === "other" ? r.dose_unit_text : label(r.dose_unit);
}

/** True while the session that started some work is still the one signed in. */
function sessionGuard(): () => boolean {
  const epoch = currentEpoch();
  return () => currentEpoch() === epoch && !isWiping() && getStatus() === "signedIn";
}

/**
 * Keeps the phone's local reminders equal to the user's schedule: re-planned when the
 * medicines, the zone or the recorded doses change, when the app comes to the foreground (the
 * 7-day window rolls on) and on request (a dose recorded or undone). One sync at a time; a
 * request during a sync runs once more after it, from the latest data. Asks for the
 * notification permission once there is something to remind of.
 */
export function useReminderSync(): void {
  const t = useTranslations("app.meds");
  const patients = usePatients();
  const own = ownProfile(patients.data);
  const meds = useMedications(own?.id);
  const zones = useZones(own?.id);
  // doses that can be recorded ahead of their reminder: taken <= 3 h early, skipped <= 2 days
  const day = localDay(new Date()).start;
  const intakes = useIntakes(
    own?.id,
    new Date(day - DAY).toISOString(),
    new Date(day + 4 * DAY).toISOString(),
  );
  const pending = usePendingDoses(own?.id);
  const appointments = useRecords(APPOINTMENTS, own?.id);
  const latest = useRef<() => Promise<void>>(async () => undefined);
  const running = useRef({ busy: false, again: false });

  latest.current = async () => {
    if (!own) return;
    const valid = sessionGuard();
    const now = Date.now();
    // each kind is re-planned only when its data is known; otherwise its scheduled reminders
    // stay as they are (an unloaded list never cancels them - security review 2.6c M3)
    const doseData = meds.data && zones.data ? { meds: meds.data, zones: zones.data } : null;
    const medicines: ReminderMedicine[] = (doseData?.meds ?? [])
      .filter((m) => m.reminders_enabled && m.is_current)
      .map((m) => ({
        id: m.id,
        name: m.name,
        unit: unitOf(m, (u) => t(`units.${u}` as "units.mg")),
        plan: planOf(m),
      }));
    const visitsKnown = appointments.data !== undefined;
    const names = await showNames().catch(() => false);
    const details = await showAppointmentDetails().catch(() => false);
    const visits = visitsKnown
      ? planAppointmentReminders(
          {
            patientId: own.id,
            appointments: ((appointments.data ?? []) as Appointment[]).map((a) => ({
              id: a.id,
              title: a.title,
              place: a.place,
              scheduledAt: Date.parse(a.scheduled_at),
              offsetsMin: a.reminder_offsets_min,
              status: a.status,
            })),
            now,
            showNames: details,
          },
          {
            title: t("notify.apptTitle"),
            when: (at) => {
              const text = formatDateTime(new Date(at).toISOString());
              return deviceZone() === HOME_TIMEZONE ? text : t("notify.ubTime", { time: text });
            },
            named: (title, when, place) => [title, when, place].filter(Boolean).join(" · "),
          },
        )
      : [];
    let permission = await Notifications.getPermissionsAsync();
    const something = medicines.length + visits.length > 0;
    if (!permission.granted && something && permission.canAskAgain && valid()) {
      permission = await Notifications.requestPermissionsAsync();
    }
    if (!permission.granted || !valid()) return; // the Home warning says reminders are off
    await registerReminderKinds({
      channel: t("notify.channel"),
      taken: t("notify.taken"),
      takenAll: t("notify.takenAll"),
      snooze: t("notify.snooze"),
      placeholder: t("notify.title"),
    });
    const recorded = new Set(doseStates(intakes.data ?? [], pending.data ?? []).keys());
    const planned = doseData
      ? planReminders(
          {
            patientId: own.id,
            medicines,
            zones: doseData.zones.switches,
            now,
            showNames: names,
            recorded,
          },
          {
            title: t("notify.title"),
            count: (n) => t("notify.count", { n }),
            item: (name, amount) => (amount ? t("notify.item", { name, amount }) : name),
            renewTitle: t("notify.renewTitle"),
            renewBody: t("notify.renewBody"),
          },
        )
      : [];
    const enabled = new Set(medicines.map((m) => m.id));
    // a "10 мин дараа" stays only for doses still to take, of medicines still reminded; its
    // text was copied when snoozed, so a change of the names setting drops it too
    const keepSnooze = (items: { m: string; at: number }[], body: string) =>
      !doseData ||
      (items.length > 0 &&
        (names || body === t("notify.count", { n: items.length })) &&
        items.every((x) => enabled.has(x.m) && !recorded.has(doseKey(x.m, x.at))));
    const keepUnplanned = (id: string) => (id.startsWith("appt.") ? !visitsKnown : !doseData);
    await syncReminders([...planned, ...visits], keepSnooze, valid, keepUnplanned);
  };

  const runRef = useRef<() => void>(() => undefined);
  runRef.current = () => {
    const state = running.current;
    if (state.busy) {
      state.again = true;
      return;
    }
    state.busy = true;
    void (async () => {
      try {
        do {
          state.again = false;
          await latest.current().catch(() => undefined);
        } while (state.again);
      } finally {
        state.busy = false;
      }
    })();
  };

  // biome-ignore lint/correctness/useExhaustiveDependencies: re-plan when the data changes
  useEffect(() => {
    runRef.current();
  }, [meds.data, zones.data, intakes.data, pending.data, appointments.data, own?.id]);

  useEffect(() => {
    const off = onReminderSync(() => runRef.current());
    const sub = AppState.addEventListener("change", (state) => {
      if (state === "active") runRef.current();
    });
    return () => {
      off();
      sub.remove();
    };
  }, []);
}

/**
 * A tap on a reminder: "Уусан" records every dose it lists (through the offline queue);
 * "10 мин дараа" schedules it once more; the reminder itself opens the Medicines tab. Also
 * handles the tap that started the app (cold start), once the app is unlocked. Only this
 * phone's own local reminders, for the signed-in user's profile and medicines, are acted on.
 */
export function useReminderResponses(): void {
  const t = useTranslations("app.meds");
  const router = useRouter();
  const patients = usePatients();
  const own = ownProfile(patients.data);
  const meds = useMedications(own?.id);
  const last = Notifications.useLastNotificationResponse();
  const handled = useRef(new Set<string>());
  const handleRef = useRef<(r: Notifications.NotificationResponse) => Promise<void>>(
    async () => undefined,
  );

  useEffect(() => {
    const handle = async (response: Notifications.NotificationResponse) => {
      const request = response.notification.request;
      Notifications.clearLastNotificationResponse();
      const trigger = request.trigger as { type?: string } | null;
      if (trigger?.type === "push") {
        // a server push only opens a screen; what it is about is read from the API (2.8f)
        void refreshNotices().catch(() => undefined);
        router.navigate(pushRoute(pushData(request.content.data)) as never);
        return;
      }
      // this phone's reminders are the user's own: their own profile opens, never the one
      // chosen for someone else (a dose logged there would be logged for them)
      setActiveProfile(null);
      if (LOCAL_APPOINTMENT_ID.test(request.identifier) && trigger?.type !== "push") {
        // an appointment reminder opens that appointment - if it is the user's own, still there
        const visit = appointmentData(request.content.data);
        const profile = ownProfile(queryClient.getQueryData<Patient[]>(patientsKey));
        const cached = profile
          ? queryClient.getQueryData<Appointment[]>(recordsKey("appointments", profile.id))
          : undefined;
        const found =
          visit && profile && visit.p === profile.id && cached?.some((a) => a.id === visit.a);
        router.navigate(found && visit ? (`/appointments/${visit.a}` as never) : "/appointments");
        return;
      }
      // only this phone's own reminders (allowlist of our ids) ever record a dose - a push
      // message never does
      const local = LOCAL_DOSE_ID.test(request.identifier) && trigger?.type !== "push";
      const data = local ? doseData(request.content.data) : null;
      // read at the tap from the cache (the signed-in user's own profile and medicines)
      const profile = ownProfile(queryClient.getQueryData<Patient[]>(patientsKey));
      const list = profile
        ? queryClient.getQueryData<Medication[]>(medicationsKey(profile.id))
        : undefined;
      const known = new Set((list ?? []).map((m) => m.id));
      const now = Date.now();
      const ours =
        data !== null &&
        profile !== undefined &&
        data.p === profile.id &&
        data.d.every((x) => known.has(x.m) && Math.abs(x.at - now) <= LOOK_AHEAD);
      if (response.actionIdentifier === ACTION_TAKEN && ours && data) {
        const valid = sessionGuard();
        let failed = false;
        for (const item of data.d) {
          if (!valid()) return;
          try {
            const result = await recordDose(data.p, {
              medicationId: item.m,
              scheduledAt: item.at,
              status: "taken",
            });
            if (result !== "queued") failed = true;
          } catch {
            failed = true;
          }
        }
        if (failed) {
          // never "recorded" when it was not: the alert says so and the list opens (the OS may
          // already have removed the reminder after the action)
          router.navigate("/meds");
          Alert.alert(t("dose.saveFailed"));
          return;
        }
        await cancelSnoozeOf(request.identifier).catch(() => undefined);
        await Notifications.dismissNotificationAsync(request.identifier).catch(() => undefined);
        return;
      }
      if (response.actionIdentifier === ACTION_TAKEN && !ours) {
        // not recorded (a medicine deleted since, a reminder of another session): say so
        router.navigate("/meds");
        Alert.alert(t("dose.saveFailed"));
        return;
      }
      if (response.actionIdentifier === ACTION_SNOOZE && ours && data) {
        await snooze(
          request.identifier,
          { title: request.content.title ?? "", body: request.content.body ?? "", data },
          sessionGuard(),
        );
        await Notifications.dismissNotificationAsync(request.identifier).catch(() => undefined);
        return;
      }
      router.navigate("/meds");
    };
    handleRef.current = handle;
    const sub = Notifications.addNotificationResponseReceivedListener((r) => {
      const key = `${r.notification.request.identifier}|${r.actionIdentifier}|${r.notification.date}`;
      if (handled.current.has(key)) return;
      handled.current.add(key);
      void handle(r).catch(() => undefined);
    });
    return () => sub.remove();
  }, [router, t]);

  // after the handler is set and the medicines are known: the tap that started the app
  useEffect(() => {
    if (!last || !meds.data || !own) return;
    const key = `${last.notification.request.identifier}|${last.actionIdentifier}|${last.notification.date}`;
    if (handled.current.has(key)) return;
    handled.current.add(key);
    void handleRef.current(last).catch(() => undefined);
  }, [last, meds.data, own]);
}
