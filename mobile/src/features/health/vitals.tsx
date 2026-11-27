import { fontSize, radius, space } from "@labtrack/shared";
import { useRouter } from "expo-router";
import { useEffect, useState } from "react";
import { Alert, StyleSheet, View } from "react-native";
import { useTranslations } from "use-intl";
import { Text } from "@/components/app-text";
import { Button } from "@/components/button";
import { Choices } from "@/components/choices";
import { FormMessage } from "@/components/form-message";
import { Screen } from "@/components/screen";
import { LoadingView, RetryView } from "@/components/state-view";
import { Paragraph, Title } from "@/components/text";
import { TextField } from "@/components/text-field";
import { currentEpoch } from "@/features/auth/session";
import { usePinnedProfile } from "@/features/records/active-profile";
import { ProfileBanner } from "@/features/records/profile-banner";
import { ProfileChanged } from "@/features/records/profile-changed";
import { formatDateTime } from "@/lib/dates";
import { localStore } from "@/lib/local-store";
import { useErrorText } from "@/lib/use-error-text";
import { usePalette } from "@/theme/use-palette";
import { useRecordProfile } from "./record-screens";
import {
  dismissFailedVital,
  recordVitals,
  useDeleteVital,
  useFailedVitals,
  usePendingVitals,
  useVitals,
  type Vital,
} from "./use-health";
import { VitalsChart } from "./vitals-chart";

/** What the user picks to enter; "bp" is one reading of upper + lower (+ pulse). */
export const ENTRY_KINDS = [
  "bp",
  "pulse",
  "weight",
  "temperature",
  "glucose",
  "spo2",
  "urine_output",
  "fluid_intake",
] as const;
export type EntryKind = (typeof ENTRY_KINDS)[number];
type SingleKind = Exclude<EntryKind, "bp">;

const UNIT: Record<SingleKind, string> = {
  pulse: "bpm",
  weight: "kg",
  temperature: "C",
  glucose: "mmol_L",
  spo2: "percent",
  urine_output: "ml",
  fluid_intake: "ml",
};

const GLUCOSE_ASKED = "prefs.glucose_unit.v1";

function useVitalText() {
  const t = useTranslations("app.health.vital");
  return (v: Vital) => t("reading", { value: v.value, unit: t(`units.${v.unit}` as "units.kg") });
}

/** Latest of each kind, the last 90 days, and "add". Values are never judged (rule 5/10). */
export function VitalsScreen() {
  const t = useTranslations("app.health.vital");
  const th = useTranslations("app.health");
  const tc = useTranslations("app.common");
  const p = usePalette();
  const router = useRouter();
  const errorText = useErrorText();
  const text = useVitalText();
  const { patients, own } = useRecordProfile();
  const vitals = useVitals(own?.id);
  const remove = useDeleteVital(own?.id ?? "");
  const failed = useFailedVitals(own?.id);
  const pending = usePendingVitals(own?.id);
  if (patients.isPending || (own && vitals.isPending)) return <LoadingView />;
  if (!own || !vitals.data) {
    return (
      <RetryView
        text={errorText(patients.error ?? vitals.error)}
        onRetry={() => void vitals.refetch()}
      />
    );
  }
  const readings = groupReadings(vitals.data);
  const latest = new Map<string, Reading>();
  for (const r of readings) if (!latest.has(r.kind)) latest.set(r.kind, r);
  const describe = (r: Reading) =>
    r.kind === "bp"
      ? [
          t("bpReading", {
            sys: r.rows.bp_systolic?.value ?? "",
            dia: r.rows.bp_diastolic?.value ?? "",
          }),
          r.rows.pulse ? text(r.rows.pulse) : null,
        ]
          .filter(Boolean)
          .join(", ")
      : text(r.rows[r.kind] as Vital);
  const what = (r: Reading) =>
    `${t(`kinds.${r.kind}` as "kinds.pulse")} ${describe(r)}, ${formatDateTime(r.at)}`;
  const confirm = (r: Reading) =>
    Alert.alert(t("deleteReading", { what: what(r) }), th("deleteConfirm"), [
      { text: tc("cancel"), style: "cancel" },
      {
        text: th("deleteYes"),
        style: "destructive",
        onPress: () => {
          for (const v of Object.values(r.rows)) if (v) remove.mutate(v.id);
        },
      },
    ]);
  const waiting = pending.data ?? [];
  return (
    <Screen>
      <ProfileBanner />
      <Paragraph muted>{t("plausibleOnly")}</Paragraph>
      <Button label={t("add")} onPress={() => router.push("/vitals/new")} />
      {remove.error && <FormMessage kind="error" text={errorText(remove.error)} />}
      {(failed.data ?? []).map((w) => (
        <View key={w.id} style={styles.failed}>
          <FormMessage kind="warning" text={t("refused", { what: queuedText(w.body) })} />
          <Button
            label={t("refusedDismiss")}
            variant="link"
            onPress={() => void dismissFailedVital(own.id, w.id)}
          />
        </View>
      ))}
      {waiting.length > 0 && (
        <View style={styles.failed}>
          <Paragraph>{t("pendingSome", { n: waiting.length })}</Paragraph>
          {waiting.map((w) => (
            <Text key={w.id} style={[styles.hint, { color: p.textMuted }]}>
              {`${t("waiting")}: ${queuedText(w.body)}`}
            </Text>
          ))}
        </View>
      )}
      <VitalsChart vitals={vitals.data} />
      <Title>{t("latest")}</Title>
      {latest.size === 0 && <Paragraph>{t("noValue")}</Paragraph>}
      {[...latest.values()].map((r) => (
        <View
          key={r.kind}
          accessible
          style={[styles.row, { borderColor: p.border, backgroundColor: p.surface }]}
        >
          <Text style={[styles.label, { color: p.text }]}>
            {t(`kinds.${r.kind}` as "kinds.pulse")}
          </Text>
          <Text style={[styles.body, { color: p.text }]}>
            {describe(r)} · {formatDateTime(r.at)}
          </Text>
        </View>
      ))}
      <Title>{t("recent")}</Title>
      {readings.map((r) => (
        <View key={r.key} style={[styles.row, { borderColor: p.border }]}>
          <Text style={[styles.body, { color: p.text }]}>
            {t(`kinds.${r.kind}` as "kinds.pulse")}: {describe(r)}
          </Text>
          <Text style={[styles.hint, { color: p.textMuted }]}>{formatDateTime(r.at)}</Text>
          <Button
            label={t("deleteReading", { what: what(r) })}
            variant="link"
            onPress={() => confirm(r)}
          />
        </View>
      ))}
    </Screen>
  );

  function queuedText(body: Record<string, unknown>): string {
    const items = Array.isArray(body.items)
      ? (body.items as { kind: string; value: string }[])
      : [];
    return items.map((i) => `${t(`kinds.${i.kind}` as "kinds.pulse")} ${i.value}`).join(", ");
  }
}

type Reading = {
  key: string;
  kind: string; // "bp" for one blood-pressure reading
  at: string;
  rows: Partial<Record<string, Vital>>;
};

/** Rows of one reading (a blood-pressure pair with its pulse) shown together, newest first. */
function groupReadings(rows: readonly Vital[]): Reading[] {
  const out: Reading[] = [];
  const groups = new Map<string, Reading>();
  for (const v of rows) {
    if (v.group_id) {
      const found = groups.get(v.group_id);
      if (found) {
        found.rows[v.kind] = v;
        continue;
      }
      const reading = { key: v.group_id, kind: "bp", at: v.measured_at, rows: { [v.kind]: v } };
      groups.set(v.group_id, reading);
      out.push(reading);
    } else {
      out.push({ key: v.id, kind: v.kind, at: v.measured_at, rows: { [v.kind]: v } });
    }
  }
  return out;
}

/**
 * Enter a reading: the unit is shown with every field (fixed per kind - glucose in mmol/L
 * only). The first glucose entry asks which unit the meter shows: a mg/dL number must never
 * be typed into the mmol/L field (medical review 2.6a H1, H26).
 */
export function VitalEntry() {
  const t = useTranslations("app.health.vital");
  const router = useRouter();
  const errorText = useErrorText();
  const { patients, own: active } = useRecordProfile();
  const { pinned: own, changed } = usePinnedProfile(active);
  const [kind, setKind] = useState<EntryKind | null>(null);
  const [values, setValues] = useState<Record<string, string>>({});
  const [note, setNote] = useState("");
  const [state, setState] = useState<"idle" | "saving" | "full">("idle");
  const [failure, setFailure] = useState<unknown>(null);
  const [glucoseUnit, setGlucoseUnit] = useState<"unknown" | "mmol" | "mgdl" | null>(null);

  // asked per profile: someone cared for may have a meter in mg/dL (H1, H26)
  const glucoseKey = own ? `${GLUCOSE_ASKED}.${own.id}` : null;
  useEffect(() => {
    if (!glucoseKey) return;
    void localStore()
      .then((s) => setGlucoseUnit((s.getString(glucoseKey) as "mmol" | undefined) ?? "unknown"))
      .catch(() => setGlucoseUnit("unknown"));
  }, [glucoseKey]);

  if (changed) return <ProfileChanged />;
  if (patients.isPending) return <LoadingView />;
  if (!own)
    return <RetryView text={errorText(patients.error)} onRetry={() => void patients.refetch()} />;

  const unitLabel = (k: SingleKind) => t(`units.${UNIT[k]}` as "units.kg");
  const items =
    kind === "bp"
      ? [
          { kind: "bp_systolic" as const, value: values.sys ?? "" },
          { kind: "bp_diastolic" as const, value: values.dia ?? "" },
          ...(values.pulse?.trim() ? [{ kind: "pulse" as const, value: values.pulse }] : []),
        ]
      : kind
        ? [{ kind, value: values.one ?? "" }]
        : [];
  const missing = items.some((i) => i.value.trim() === "");
  const askGlucose = kind === "glucose" && glucoseUnit !== "mmol";
  const blocked = kind === "glucose" && glucoseUnit !== "mmol";

  const save = async () => {
    if (!kind || missing) return;
    setState("saving");
    setFailure(null);
    try {
      const result = await recordVitals(
        own.id,
        items.map((i) => ({ kind: i.kind, value: i.value.trim() })),
        note.trim() === "" ? null : note.trim(),
        currentEpoch(),
      );
      if (result === "full") {
        setState("full");
        return;
      }
      router.back();
    } catch (exc) {
      setFailure(exc);
      setState("idle");
    }
  };

  return (
    <Screen>
      <ProfileBanner />
      <Choices
        label={t("choose")}
        options={ENTRY_KINDS}
        value={kind}
        labelOf={(k) => t(`kinds.${k}` as "kinds.bp")}
        onSelect={(k) => {
          setKind(k);
          setValues({});
        }}
        columns={2}
      />
      {kind === "glucose" && glucoseUnit === "mmol" && (
        <>
          <Paragraph>{t("glucoseUnitIs")}</Paragraph>
          <Button
            label={t("glucoseChange")}
            variant="link"
            onPress={() => {
              setGlucoseUnit("unknown");
              void localStore()
                .then((s) => s.remove(GLUCOSE_ASKED))
                .catch(() => undefined);
            }}
          />
        </>
      )}
      {askGlucose && (
        <>
          <Choices
            label={t("glucoseAsk")}
            options={["mmol", "mgdl"] as const}
            value={glucoseUnit === "unknown" ? null : glucoseUnit}
            labelOf={(u) => t(u === "mmol" ? "glucoseMmol" : "glucoseMgdl")}
            onSelect={(u) => {
              setGlucoseUnit(u);
              if (u === "mmol" && glucoseKey)
                void localStore().then((s) => s.set(glucoseKey, "mmol"));
            }}
          />
          {glucoseUnit === "mgdl" && <FormMessage kind="warning" text={t("glucoseMgdlNote")} />}
        </>
      )}
      {kind === "bp" && (
        <>
          <TextField
            label={t("systolic")}
            value={values.sys ?? ""}
            keyboardType="number-pad"
            maxLength={3}
            onChangeText={(sys) => setValues((v) => ({ ...v, sys }))}
          />
          <TextField
            label={t("diastolic")}
            value={values.dia ?? ""}
            keyboardType="number-pad"
            maxLength={3}
            onChangeText={(dia) => setValues((v) => ({ ...v, dia }))}
          />
          <TextField
            label={t("pulseOptional")}
            value={values.pulse ?? ""}
            keyboardType="number-pad"
            maxLength={3}
            onChangeText={(pulse) => setValues((v) => ({ ...v, pulse }))}
          />
        </>
      )}
      {kind && kind !== "bp" && !blocked && (
        <TextField
          label={t("value", { kind: t(`kinds.${kind}` as "kinds.pulse"), unit: unitLabel(kind) })}
          value={values.one ?? ""}
          keyboardType="decimal-pad"
          maxLength={8}
          onChangeText={(one) => setValues((v) => ({ ...v, one }))}
        />
      )}
      {kind && <TextField label={t("note")} value={note} maxLength={200} onChangeText={setNote} />}
      {state === "full" && <FormMessage kind="error" text={t("queueFull")} />}
      {failure !== null && <FormMessage kind="error" text={errorText(failure)} />}
      {kind && !blocked && (
        <Button
          label={t("save")}
          disabled={missing}
          busy={state === "saving"}
          onPress={() => void save()}
        />
      )}
      <Paragraph muted>{t("pending")}</Paragraph>
    </Screen>
  );
}

const styles = StyleSheet.create({
  row: {
    gap: space.xs,
    padding: space.sm,
    borderRadius: radius.md,
    borderWidth: StyleSheet.hairlineWidth * 2,
  },
  label: { fontSize: fontSize.body, fontWeight: "600" },
  body: { fontSize: fontSize.body, lineHeight: fontSize.body * 1.4 },
  hint: { fontSize: fontSize.caption },
  failed: { gap: space.xs },
});
