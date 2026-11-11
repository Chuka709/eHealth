import { fontSize, radius, space } from "@labtrack/shared";
import { useEffect, useRef, useState } from "react";
import { Alert, StyleSheet, Text, View } from "react-native";
import { useTranslations } from "use-intl";

import { Button } from "@/components/button";
import { FormMessage } from "@/components/form-message";
import { usePalette } from "@/theme/use-palette";

import type { TodayDose } from "./plan";
import {
  currentRecord,
  dismissFailedDose,
  type IntakeStatus,
  recordDose,
  settle,
  undoDose,
  useFailedDoses,
} from "./use-medications";

const formatters = new Map<string, Intl.DateTimeFormat>();

/** "HH:MM" in a zone, 24 h. "en-US" is deliberate: only the digits are read (formatToParts),
 * so the output is the same whatever the app language. */
export function clockIn(ms: number, zone: string): string {
  let f = formatters.get(zone);
  if (!f) {
    f = new Intl.DateTimeFormat("en-US", {
      timeZone: zone,
      hour: "2-digit",
      minute: "2-digit",
      hourCycle: "h23",
    });
    formatters.set(zone, f);
  }
  const parts = f.formatToParts(new Date(ms));
  const get = (type: string) => parts.find((x) => x.type === type)?.value ?? "";
  return `${get("hour")}:${get("minute")}`;
}

type Notice = "full" | "saveFailed" | "undoFailed" | null;

/**
 * Today's planned doses, each with "Уусан" / "Алгассан", and "Буцаах" once recorded. Recorded
 * ones say so in words with a glyph (never colour alone); a dose not yet due says so, and
 * nothing is ever called late or missed (Q23).
 */
export function TodayList({
  patientId,
  doses,
  now,
}: {
  patientId: string;
  doses: TodayDose[];
  now: number;
}) {
  const t = useTranslations("app.meds");
  const p = usePalette();
  const [notice, setNotice] = useState<Notice>(null);
  const [busy, setBusy] = useState<string | null>(null);
  // a second tap on "Уусан" must not land on the "Буцаах" that replaces it
  const [settling, setSettling] = useState<string | null>(null);

  const inFlight = useRef(new Set<string>());
  // a profile switch while the server is asked unmounts this list: no question about the
  // previous person's dose may then appear over another profile (H20)
  const mounted = useRef(true);
  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
    };
  }, []);
  const run = async (key: string, work: () => Promise<Notice>) => {
    // one tap at a time per dose, checked synchronously: a double tap never queues twice
    if (inFlight.current.has(key)) return;
    inFlight.current.add(key);
    setBusy(key);
    try {
      setNotice(await work());
    } finally {
      inFlight.current.delete(key);
      setBusy((k) => (k === key ? null : k));
      setSettling(key);
      setTimeout(() => setSettling((k) => (k === key ? null : k)), 1000);
    }
  };
  const save = (dose: TodayDose, key: string, status: IntakeStatus) =>
    run(key, async () => {
      try {
        const result = await recordDose(patientId, {
          medicationId: dose.medication.id,
          scheduledAt: dose.slot.scheduledAt,
          status,
        });
        return result === "full" ? "full" : null;
      } catch {
        return "saveFailed";
      }
    });
  // Q24: someone may already have recorded this dose taken - said before, never judged
  const mark = async (dose: TodayDose, key: string, status: IntakeStatus) => {
    if (status !== "taken" || inFlight.current.has(key)) return save(dose, key, status);
    // held while asking the server: a second tap meanwhile does nothing
    const checking = `${key}#check`;
    if (inFlight.current.has(checking)) return;
    inFlight.current.add(checking);
    let stored: Awaited<ReturnType<typeof currentRecord>>;
    try {
      stored = await currentRecord(patientId, dose.medication.id, dose.slot.scheduledAt);
    } finally {
      inFlight.current.delete(checking);
    }
    if (!mounted.current) return settle(patientId);
    // the list may have been closed (a profile switch) while the question was open
    const record = () => (mounted.current ? void save(dose, key, status) : settle(patientId));
    if (stored === "unknown") {
      Alert.alert(
        t("dose.uncheckedTitle"),
        t("dose.uncheckedBody"),
        [
          { text: t("dose.alreadyCancel"), style: "cancel", onPress: () => settle(patientId) },
          { text: t("dose.alreadyRecord"), onPress: record },
        ],
        { cancelable: true },
      );
      return;
    }
    if (!stored?.taken_at) return save(dose, key, status);
    const who = t(`dose.who.${stored.recorded_by ?? "someone"}` as "dose.who.you");
    const time = clockIn(Date.parse(stored.taken_at), dose.zone);
    Alert.alert(
      t("dose.alreadyTitle"),
      stored.recorded_by === "you"
        ? t("dose.alreadyBodyYou", { time })
        : t("dose.alreadyBody", { time, who }),
      [
        { text: t("dose.alreadyCancel"), style: "cancel", onPress: () => settle(patientId) },
        { text: t("dose.alreadyRecord"), onPress: record },
      ],
      { cancelable: true },
    );
  };
  const undo = (dose: TodayDose, key: string) =>
    run(key, async () => {
      if (!dose.recorded) return "undoFailed";
      try {
        await undoDose(patientId, {
          medicationId: dose.medication.id,
          scheduledAt: dose.slot.scheduledAt,
          pendingIds: dose.recorded.pendingIds,
          stored:
            dose.recorded.intakeId !== null &&
            !dose.recorded.pendingIds.includes(dose.recorded.intakeId),
        });
        return null;
      } catch {
        return "undoFailed";
      }
    });

  return (
    <View style={styles.list}>
      <FailedDoses patientId={patientId} doses={doses} />
      {notice && (
        <FormMessage
          kind="error"
          text={t(notice === "full" ? "dose.queueFull" : `dose.${notice}`)}
        />
      )}
      {doses.length === 0 && (
        <Text style={[styles.body, { color: p.text }]}>{t("todayEmpty")}</Text>
      )}
      {doses.map((dose) => {
        const key = `${dose.medication.id}@${dose.slot.scheduledAt}@${dose.slot.at}`;
        return (
          <DoseRow
            key={key}
            dose={dose}
            due={dose.slot.scheduledAt <= now}
            busy={busy === key}
            settling={settling === key}
            onMark={(status) => void mark(dose, key, status)}
            onUndo={() => void undo(dose, key)}
          />
        );
      })}
    </View>
  );
}

function DoseRow({
  dose,
  due,
  busy,
  settling,
  onMark,
  onUndo,
}: {
  dose: TodayDose;
  due: boolean;
  busy: boolean;
  settling: boolean;
  onMark: (s: IntakeStatus) => void;
  onUndo: () => void;
}) {
  const t = useTranslations("app.meds");
  const p = usePalette();
  const time = clockIn(dose.slot.scheduledAt, dose.zone);
  const regimen = dose.medication.current_regimen ?? dose.medication.regimens[0];
  const unit = regimen?.dose_unit
    ? regimen.dose_unit === "other"
      ? (regimen.dose_unit_text ?? "")
      : t(`units.${regimen.dose_unit}` as "units.mg")
    : "";
  const amount = dose.slot.amount ? `${dose.slot.amount} ${unit}`.trim() : null;
  const name = dose.medication.name;
  const who = (by: string | null | undefined) => t(`dose.who.${by ?? "someone"}` as "dose.who.you");
  const at = (iso: string) => clockIn(Date.parse(iso), dose.zone);
  const state =
    dose.state === "taken"
      ? dose.recorded?.takenAt &&
        (dose.recorded.by === "owner" ||
          dose.recorded.by === "caregiver" ||
          // with other records beside it, the first one's time matters too
          (dose.recorded.by === "you" && (dose.recorded.also?.length ?? 0) > 0))
        ? t("dose.stateTakenBy", { who: who(dose.recorded.by), time: at(dose.recorded.takenAt) })
        : t("dose.stateTaken")
      : dose.state === "skipped"
        ? t("dose.stateSkipped")
        : due
          ? t("dose.stateNone")
          : t("dose.upcoming");
  return (
    <View
      style={[styles.row, { backgroundColor: p.surface, borderColor: p.border }]}
      testID={`dose-${dose.medication.id}-${dose.slot.at}`}
    >
      <Text style={[styles.title, { color: p.text }]}>
        {time} · {name}
      </Text>
      {amount && <Text style={[styles.body, { color: p.text }]}>{amount}</Text>}
      {/* stays mounted: a change of state is read out where the buttons were */}
      <Text
        accessibilityLiveRegion="polite"
        style={[styles.body, { color: dose.state ? p.text : p.textMuted }]}
      >
        {state}
      </Text>
      {(dose.recorded?.also ?? []).map((x) => (
        <Text key={`${x.by}@${x.takenAt}`} style={[styles.body, { color: p.text }]}>
          {t("dose.alsoRecorded", { who: who(x.by), time: at(x.takenAt) })}
        </Text>
      ))}
      {dose.state === null ? (
        <View style={styles.actions}>
          <View style={styles.action}>
            <Button
              label={t("dose.taken")}
              accessibilityLabel={t("dose.markTaken", { time, name })}
              busy={busy}
              onPress={() => onMark("taken")}
            />
          </View>
          <View style={styles.action}>
            <Button
              label={t("dose.skipped")}
              accessibilityLabel={t("dose.markSkipped", { time, name })}
              variant="secondary"
              disabled={busy}
              onPress={() => onMark("skipped")}
            />
          </View>
        </View>
      ) : (
        <Button
          label={t("dose.undo")}
          accessibilityLabel={t("dose.undoLabel", { time, name })}
          variant="link"
          busy={busy}
          disabled={settling}
          onPress={onUndo}
        />
      )}
    </View>
  );
}

/** Records the server refused: shown until the user has seen them (never dropped silently). */
function FailedDoses({ patientId, doses }: { patientId: string; doses: TodayDose[] }) {
  const t = useTranslations("app.meds");
  const failed = useFailedDoses(patientId);
  if (!failed.data?.length) return null;
  const nameOf = (id: unknown) => doses.find((d) => d.medication.id === id)?.medication.name ?? "";
  return (
    <View style={styles.list} testID="failed-doses">
      {failed.data.map((w) => {
        const at = Date.parse(String(w.body.scheduled_at));
        const zone = doses.find((d) => d.medication.id === w.body.medication_id)?.zone;
        const time = Number.isFinite(at) ? clockIn(at, zone ?? "Asia/Ulaanbaatar") : "";
        return (
          <View key={w.id} style={styles.list}>
            <FormMessage
              kind="warning"
              text={`${t("failed.title")}. ${t("failed.item", { time, name: nameOf(w.body.medication_id) })}`}
            />
            <Button
              label={t("failed.dismiss")}
              variant="link"
              onPress={() => void dismissFailedDose(patientId, w.id)}
            />
          </View>
        );
      })}
    </View>
  );
}

const styles = StyleSheet.create({
  list: { gap: space.md },
  row: {
    gap: space.xs,
    padding: space.md,
    borderRadius: radius.md,
    borderWidth: StyleSheet.hairlineWidth * 2,
  },
  title: { fontSize: fontSize.bodyLarge, fontWeight: "700" },
  body: { fontSize: fontSize.body, lineHeight: fontSize.body * 1.4 },
  actions: { flexDirection: "row", flexWrap: "wrap", gap: space.sm, marginTop: space.sm },
  action: { flexBasis: "47%", flexGrow: 1 },
});
