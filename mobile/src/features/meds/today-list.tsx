import { fontSize, radius, space } from "@labtrack/shared";
import { useEffect, useRef, useState } from "react";
import { Alert, StyleSheet, View } from "react-native";
import { useTranslations } from "use-intl";
import { Text } from "@/components/app-text";
import { Button } from "@/components/button";
import { FormMessage } from "@/components/form-message";
import { Icon } from "@/components/icon";
import { usePalette } from "@/theme/use-palette";

import type { TodayDose } from "./plan";
import type { Medication } from "./use-medications";
import {
  currentRecord,
  dismissFailedDose,
  type IntakeStatus,
  recordDose,
  settle,
  undoDose,
  useFailedDoses,
} from "./use-medications";

/** A taken dose this far from its time shows how far (Q25); closer, nothing is said. */
const OFFSET_SHOWN_MIN = 30;

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
  waiting = [],
}: {
  patientId: string;
  doses: TodayDose[];
  now: number;
  /** "local" medicines whose doses wait for the profile's zones (see useTodayDoses) */
  waiting?: readonly Medication[];
}) {
  const t = useTranslations("app.meds");
  const p = usePalette();
  const [notice, setNotice] = useState<Notice>(null);
  const [busy, setBusy] = useState<string | null>(null);
  // a second tap on "Уусан" must not land on the "Буцаах" that replaces it
  const [settling, setSettling] = useState<string | null>(null);
  // Q24: while the server is asked (up to CHECK_TIMEOUT_MS) the tap must visibly be in hand
  const [checking, setChecking] = useState<string | null>(null);
  // "Бүгдийг уусан" of one dose time in hand (UX audit #2)
  const [groupBusy, setGroupBusy] = useState<string | null>(null);
  // later dose times folded away until asked for (UX audit #2)
  const [showLater, setShowLater] = useState(false);

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
    const checkKey = `${key}#check`;
    if (inFlight.current.has(checkKey)) return;
    inFlight.current.add(checkKey);
    setChecking(key);
    let stored: Awaited<ReturnType<typeof currentRecord>>;
    try {
      stored = await currentRecord(patientId, dose.medication.id, dose.slot.scheduledAt);
    } finally {
      inFlight.current.delete(checkKey);
      if (mounted.current) setChecking((k) => (k === key ? null : k));
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
        { cancelable: true, onDismiss: () => settle(patientId) },
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
      { cancelable: true, onDismiss: () => settle(patientId) },
    );
  };
  /**
   * "Бүгдийг уусан" for one dose time (UX audit #2). Each dose is checked first (Q24): if any
   * is already recorded - by anyone - or cannot be checked, nothing is recorded and the user is
   * asked to record them one by one, where each says who recorded what (never a double dose by
   * one tap). Otherwise every open dose of that time is recorded taken.
   */
  const markGroup = async (groupKey: string, items: TodayDose[]) => {
    const open = items.filter((d) => d.state === null);
    const keys = open.map(doseKey);
    // never while one of its doses is being recorded or checked on its own (ui review M3)
    if (
      open.length < 2 ||
      inFlight.current.has(groupKey) ||
      keys.some((k) => inFlight.current.has(k) || inFlight.current.has(`${k}#check`))
    ) {
      return;
    }
    inFlight.current.add(groupKey);
    // and the other way: a dose's own "Уусан" waits while the group is recorded
    for (const k of keys) inFlight.current.add(k);
    setGroupBusy(groupKey);
    try {
      const stored = await Promise.all(
        open.map((d) =>
          currentRecord(patientId, d.medication.id, d.slot.scheduledAt, { anyStatus: true }),
        ),
      );
      if (!mounted.current) return settle(patientId);
      if (stored.some((s) => s !== null)) {
        Alert.alert(t("dose.groupOneByOneTitle"), t("dose.groupOneByOneBody"), [
          { text: t("dose.groupOneByOneOk"), onPress: () => settle(patientId) },
        ]);
        return;
      }
      // every medicine and amount said before one tap records them all: a dose not taken is
      // never recorded taken by accident (medical review M1)
      const time = open[0] ? clockIn(open[0].slot.scheduledAt, open[0].zone) : "";
      const sure = await new Promise<boolean>((resolve) =>
        Alert.alert(
          t("dose.groupConfirmTitle", { time }),
          t("dose.groupConfirmBody", {
            list: open.map((d) => `• ${doseLabel(d)}`).join("\n"),
          }),
          [
            { text: t("dose.alreadyCancel"), style: "cancel", onPress: () => resolve(false) },
            { text: t("dose.groupTaken"), onPress: () => resolve(true) },
          ],
          { cancelable: true, onDismiss: () => resolve(false) },
        ),
      );
      if (!sure || !mounted.current) return settle(patientId);
      let failed: Notice = null;
      for (const d of open) {
        if (!mounted.current) {
          settle(patientId); // closed meanwhile: the list is read again, the rest not recorded
          break;
        }
        try {
          const result = await recordDose(patientId, {
            medicationId: d.medication.id,
            scheduledAt: d.slot.scheduledAt,
            status: "taken",
          });
          if (result === "full") failed = "full";
        } catch {
          failed = "saveFailed";
        }
      }
      if (mounted.current) setNotice(failed);
    } finally {
      inFlight.current.delete(groupKey);
      for (const k of keys) inFlight.current.delete(k);
      if (mounted.current) setGroupBusy((k) => (k === groupKey ? null : k));
    }
  };
  /** "Такролимус 2 мг": the medicine and the amount of this dose, as its row shows them. */
  const doseLabel = (d: TodayDose) => {
    const regimen = d.medication.current_regimen ?? d.medication.regimens[0];
    const unit = regimen?.dose_unit
      ? regimen.dose_unit === "other"
        ? (regimen.dose_unit_text ?? "")
        : t(`units.${regimen.dose_unit}` as "units.mg")
      : "";
    const amount = d.slot.amount ? `${d.slot.amount} ${unit}`.trim() : "";
    return amount ? `${d.medication.name} ${amount}` : d.medication.name;
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

  const groups = byTime(doses);
  const { shown, later } = splitLater(groups, now);
  const visible = showLater ? groups : shown;

  return (
    <View style={styles.list}>
      <FailedDoses patientId={patientId} doses={doses} />
      {notice && (
        <FormMessage
          kind="error"
          text={t(notice === "full" ? "dose.queueFull" : `dose.${notice}`)}
        />
      )}
      {waiting.length > 0 && (
        <FormMessage
          kind="warning"
          text={t("zoneWait", { names: waiting.map((m) => m.name).join(", ") })}
        />
      )}
      {doses.length === 0 && waiting.length === 0 && (
        <Text style={[styles.body, { color: p.text }]}>{t("todayEmpty")}</Text>
      )}
      {visible.map(({ key: groupKey, time, items }) => (
        <View key={groupKey} style={styles.group}>
          <View style={styles.groupHead}>
            {/* the time only: Home lists a part of the day, so a count here could mislead */}
            <Text accessibilityRole="header" style={[styles.groupTime, { color: p.text }]}>
              {time}
            </Text>
            {/* due times only: a dose not yet due is recorded on its own (ui review M2, Q25) */}
            {(items[0]?.slot.scheduledAt ?? Number.POSITIVE_INFINITY) <= now &&
              items.filter((d) => d.state === null).length >= 2 && (
                <Button
                  compact
                  variant="secondary"
                  label={t("dose.groupTaken")}
                  accessibilityLabel={t("dose.groupTakenLabel", {
                    time,
                    n: items.filter((d) => d.state === null).length,
                  })}
                  busy={
                    groupBusy === groupKey ||
                    items.some((d) => busy === doseKey(d) || checking === doseKey(d))
                  }
                  onPress={() => void markGroup(groupKey, items)}
                />
              )}
          </View>
          <View style={[styles.card, { backgroundColor: p.surface, borderColor: p.border }]}>
            {items.map((dose, i) => {
              const key = doseKey(dose);
              return (
                <DoseRow
                  key={key}
                  first={i === 0}
                  dose={dose}
                  due={dose.slot.scheduledAt <= now}
                  busy={busy === key || checking === key || groupBusy === groupKey}
                  checking={checking === key}
                  settling={settling === key}
                  onMark={(status) => void mark(dose, key, status)}
                  onUndo={() => void undo(dose, key)}
                />
              );
            })}
          </View>
        </View>
      ))}
      {later.length > 0 && (
        <Button
          variant="link"
          label={
            showLater
              ? t("dose.laterHide")
              : t("dose.laterTimes", { n: later.reduce((n, g) => n + g.items.length, 0) })
          }
          expanded={showLater}
          onPress={() => setShowLater(!showLater)}
        />
      )}
    </View>
  );
}

/** One dose of the list, for busy states and the one-tap-at-a-time guard. */
const doseKey = (dose: TodayDose) =>
  `${dose.medication.id}@${dose.slot.scheduledAt}@${dose.slot.at}`;

/**
 * The times shown at once: every time already due (an open dose there matters now) and the next
 * one to come; the later ones of the day fold away behind one line (UX audit #2). A list with
 * nothing due yet shows the first time.
 */
export function splitLater<G extends { items: readonly TodayDose[] }>(
  groups: readonly G[],
  now: number,
): { shown: G[]; later: G[] } {
  const firstFuture = groups.findIndex((g) => (g.items[0]?.slot.scheduledAt ?? 0) > now);
  if (firstFuture === -1) return { shown: [...groups], later: [] };
  return { shown: groups.slice(0, firstFuture + 1), later: groups.slice(firstFuture + 1) };
}

/**
 * Doses grouped by the clock time shown (2.12): a day is lived by its dose times. Only doses of
 * the same instant share a group - the same "08:00" text at another instant (a "local" medicine
 * in another zone, a DST repeat) is a group of its own, keyed by its instant (medical review).
 */
export function byTime(
  doses: readonly TodayDose[],
): { key: string; time: string; items: TodayDose[] }[] {
  const groups: { key: string; time: string; at: number; items: TodayDose[] }[] = [];
  for (const dose of doses) {
    const time = clockIn(dose.slot.scheduledAt, dose.zone);
    const at = dose.slot.scheduledAt;
    const last = groups.at(-1);
    if (last && last.time === time && last.at === at) last.items.push(dose);
    else groups.push({ key: `${time}@${at}@${groups.length}`, time, at, items: [dose] });
  }
  return groups;
}

function DoseRow({
  first,
  dose,
  due,
  busy,
  checking,
  settling,
  onMark,
  onUndo,
}: {
  first: boolean;
  dose: TodayDose;
  due: boolean;
  busy: boolean;
  /** "Уусан" tapped, the server is asked whether it is already recorded (Q24) */
  checking: boolean;
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
  const state = checking
    ? t("dose.checking")
    : dose.state === "taken"
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
  const recorded = dose.state !== null;
  // how far from its time the dose was taken, as a fact - never "late" (Q23, Q25: no judgement)
  const offset =
    dose.state === "taken" && dose.recorded?.takenAt
      ? Math.round((Date.parse(dose.recorded.takenAt) - dose.slot.scheduledAt) / 60_000)
      : 0;
  const offsetText =
    Math.abs(offset) >= OFFSET_SHOWN_MIN
      ? t(offset > 0 ? "dose.takenAfter" : "dose.takenBefore", {
          hours: Math.floor(Math.abs(offset) / 60),
          minutes: Math.abs(offset) % 60,
        })
      : null;
  return (
    <View
      style={[
        styles.row,
        !first && { borderTopColor: p.border, borderTopWidth: StyleSheet.hairlineWidth },
      ]}
      testID={`dose-${dose.medication.id}-${dose.slot.at}`}
    >
      <View style={styles.line}>
        <View style={styles.what}>
          <Text style={[styles.name, { color: p.text }]}>{name}</Text>
          {amount && <Text style={[styles.body, { color: p.textMuted }]}>{amount}</Text>}
        </View>
        {dose.state === null && (
          // stays on the right even when a large font wraps it onto its own line
          <View style={styles.primary}>
            <Button
              compact
              label={t("dose.taken")}
              accessibilityLabel={t("dose.markTaken", { time, name })}
              busy={busy}
              onPress={() => onMark("taken")}
            />
          </View>
        )}
      </View>
      {/* stays mounted: a change of state is read out where the buttons were */}
      <View style={styles.stateLine}>
        {/* the state's mark, beside its words (never colour alone) */}
        {dose.state === "taken" && <Icon name="check-circle" color={p.done.fg} size={18} />}
        {dose.state === "skipped" && (
          <Icon name="minus-circle-outline" color={p.textMuted} size={18} />
        )}
        <Text
          accessibilityLiveRegion="polite"
          style={[
            styles.body,
            styles.stateText,
            { color: dose.state === "taken" ? p.done.fg : recorded ? p.text : p.textMuted },
          ]}
        >
          {state}
        </Text>
        {offsetText && (
          <Text style={[styles.body, { color: p.textMuted }]} testID="dose-offset">
            {offsetText}
          </Text>
        )}
      </View>
      {(dose.recorded?.also ?? []).map((x) => (
        <Text key={`${x.by}@${x.takenAt}`} style={[styles.body, { color: p.text }]}>
          {t("dose.alsoRecorded", { who: who(x.by), time: at(x.takenAt) })}
        </Text>
      ))}
      <View style={styles.secondary}>
        {dose.state === null ? (
          // a deliberate choice: outlined, at the left, away from "Уусан" (2.12 medical review)
          <Button
            compact
            label={t("dose.skipped")}
            accessibilityLabel={t("dose.markSkipped", { time, name })}
            variant="secondary"
            disabled={busy}
            onPress={() => onMark("skipped")}
          />
        ) : (
          <Button
            compact
            label={t("dose.undo")}
            accessibilityLabel={t("dose.undoLabel", { time, name })}
            variant="quiet"
            busy={busy}
            disabled={settling}
            onPress={onUndo}
          />
        )}
      </View>
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
  group: { gap: space.sm },
  groupHead: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    flexWrap: "wrap",
    gap: space.sm,
  },
  groupTime: {
    fontSize: fontSize.title,
    fontWeight: "700",
    fontVariant: ["tabular-nums"],
  },
  card: {
    borderRadius: radius.lg,
    borderWidth: StyleSheet.hairlineWidth,
    overflow: "hidden",
  },
  row: { gap: space.sm, paddingHorizontal: space.lg, paddingVertical: space.md },
  line: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    flexWrap: "wrap",
    gap: space.md,
  },
  what: { flexGrow: 1, flexShrink: 1, flexBasis: 160, gap: 2 },
  name: { fontSize: fontSize.bodyLarge, fontWeight: "600" },
  stateLine: { flexDirection: "row", alignItems: "center", flexWrap: "wrap", gap: space.xs },
  stateText: { flexShrink: 1 },
  secondary: { flexDirection: "row" },
  primary: { marginLeft: "auto" },
  body: { fontSize: fontSize.body, lineHeight: fontSize.body * 1.4 },
});
