import { useEffect, useRef } from "react";
import { Alert, AppState } from "react-native";
import { useTranslations } from "use-intl";

import { currentEpoch } from "@/features/auth/session";
import { enqueue, flush } from "@/features/offline/queue";
import { sendQueued } from "@/features/offline/use-local-data";
import { ownProfile, usePatients } from "@/features/records/use-profile";
import { localStore } from "@/lib/local-store";
import { queryClient } from "@/lib/query-client";
import { newClientId } from "@/lib/random";

import { useMedications, useZones } from "./use-medications";

const ASKED_KEY = "prefs.zone_asked.v1";

/** "Asia/Seoul (GMT+9)" - the zone with its current offset, readable in either language. */
export function zoneLabel(zone: string): string {
  try {
    const name = new Intl.DateTimeFormat("en-US", { timeZone: zone, timeZoneName: "shortOffset" })
      .formatToParts(new Date())
      .find((p) => p.type === "timeZoneName")?.value;
    return name ? `${zone.replace(/_/g, " ")} (${name})` : zone;
  } catch {
    return zone;
  }
}

export function deviceZone(): string | null {
  try {
    return Intl.DateTimeFormat().resolvedOptions().timeZone || null;
  } catch {
    return null;
  }
}

/**
 * H7: when the phone's time zone is not the profile's reminder zone and a medicine follows
 * "time where I am", ask once per zone whether to move those reminders (never silently).
 * "Home" medicines stay on Ulaanbaatar time either way. The answer is queued (works
 * offline): the switch takes effect from the moment the user said yes.
 */
export function useZonePrompt(): void {
  const t = useTranslations("app.meds.zone");
  const patients = usePatients();
  const own = ownProfile(patients.data);
  const meds = useMedications(own?.id);
  const zones = useZones(own?.id);
  const check = useRef<() => Promise<void>>(async () => undefined);
  const open = useRef(false);

  check.current = async () => {
    if (open.current || !own || !meds.data || !zones.data) return;
    const zone = deviceZone();
    if (!zone) return;
    const store = await localStore();
    if (zone === zones.data.current) {
      store.remove(ASKED_KEY); // back in the profile's zone: a later trip is asked again
      return;
    }
    const local = meds.data.some(
      (m) => m.is_current && m.reminders_enabled && m.reminder_timezone_mode === "local",
    );
    if (!local) return;
    if (store.getString(ASKED_KEY) === `${own.id}|${zone}`) return;
    open.current = true;
    const epoch = currentEpoch(); // a press after a sign-out or another sign-in does nothing
    const answered = () => {
      open.current = false;
      if (currentEpoch() === epoch) store.set(ASKED_KEY, `${own.id}|${zone}`);
    };
    Alert.alert(
      t("askTitle"),
      t("askBody", { zone: zoneLabel(zone) }),
      [
        {
          text: t("keep"),
          style: "cancel",
          onPress: () => {
            if (currentEpoch() === epoch) answered();
          },
        },
        {
          text: t("switch"),
          onPress: () => {
            // remembered only once saved: a failed switch is asked again next time
            if (currentEpoch() !== epoch) return;
            void switchZone(own.id, zone, epoch)
              .then(answered)
              .catch(() => {
                open.current = false;
                Alert.alert(t("failed"));
              });
          },
        },
      ],
      { cancelable: false },
    );
  };

  // biome-ignore lint/correctness/useExhaustiveDependencies: re-run when the data changes
  useEffect(() => {
    void check.current().catch(() => undefined);
  }, [own?.id, meds.data, zones.data]);

  useEffect(() => {
    const sub = AppState.addEventListener("change", (state) => {
      if (state === "active") void check.current().catch(() => undefined);
    });
    return () => sub.remove();
  }, []);
}

async function switchZone(patientId: string, timezone: string, epoch: number): Promise<void> {
  const clientId = newClientId();
  const queued = await enqueue(
    {
      id: clientId,
      method: "POST",
      path: `/api/v1/patients/${patientId}/timezone`,
      body: { client_id: clientId, timezone, effective_at: new Date().toISOString() },
    },
    epoch,
  );
  if (!queued) throw new Error("queue full");
  // until the server has it, the phone plans with the new zone at once
  queryClient.setQueryData(["timezone", patientId], (old: unknown) => {
    if (!old || typeof old !== "object") return old;
    const zones = old as { home: string; current: string; switches: unknown[] };
    return {
      ...zones,
      current: timezone,
      switches: [
        { id: clientId, timezone, effective_at: new Date().toISOString(), seq: 0, created_at: "" },
        ...zones.switches,
      ],
    };
  });
  await flush(sendQueued).catch(() => undefined);
  void queryClient.invalidateQueries({ queryKey: ["timezone", patientId] });
}
