import { fontSize, radius, space } from "@labtrack/shared";
import { useLocalSearchParams, useRouter } from "expo-router";
import { useState } from "react";
import { Alert, StyleSheet, Text, View } from "react-native";
import { useTranslations } from "use-intl";

import { Button } from "@/components/button";
import { PickerField } from "@/components/date-field";
import { FormMessage } from "@/components/form-message";
import { Screen } from "@/components/screen";
import { LoadingView, RetryView } from "@/components/state-view";
import { Paragraph, Title } from "@/components/text";
import { TextField } from "@/components/text-field";
import { useRegimenText } from "@/features/meds/use-med-text";
import {
  type Medication,
  type MedicationFields,
  useDeleteMedication,
  useMedications,
  useUpdateMedication,
  useVoidDose,
} from "@/features/meds/use-medications";
import { ownProfile, usePatients } from "@/features/records/use-profile";
import { formatDate } from "@/lib/dates";
import { useErrorText } from "@/lib/use-error-text";
import { usePalette } from "@/theme/use-palette";

const day = (iso: string) => formatDate(`${iso}T12:00:00Z`);

/** The fields a PUT keeps unchanged (the record as stored, with the given changes). */
function fieldsOf(m: Medication, patch: Partial<MedicationFields>): MedicationFields {
  return {
    catalog_code: m.catalog_code,
    name: m.name,
    brand: m.brand,
    form: m.form,
    strength: m.strength,
    route: m.route,
    purpose: m.purpose,
    prescribed_by: m.prescribed_by,
    transplant_id: m.transplant_id,
    started_on: m.started_on,
    stopped_on: m.stopped_on,
    stop_reason: m.stop_reason,
    planned_end_on: m.planned_end_on,
    is_long_term: m.is_long_term,
    reminders_enabled: m.reminders_enabled,
    reminder_timezone_mode: m.reminder_timezone_mode === "local" ? "local" : "home",
    notes: m.notes,
    ...patch,
  };
}

export default function MedicationScreen() {
  const t = useTranslations("app.meds");
  const tc = useTranslations("app.common");
  const p = usePalette();
  const router = useRouter();
  const errorText = useErrorText();
  const regimenText = useRegimenText();
  const { id } = useLocalSearchParams<{ id: string }>();
  const patients = usePatients();
  const own = ownProfile(patients.data);
  const meds = useMedications(own?.id, { fresh: true });
  const update = useUpdateMedication(own?.id ?? "", id);
  const voidDose = useVoidDose(own?.id ?? "", id);
  const remove = useDeleteMedication(own?.id ?? "", id);
  const [voiding, setVoiding] = useState(false);
  const [voidReason, setVoidReason] = useState("");
  const [stopping, setStopping] = useState(false);
  // never preset: the user says from which day (as for a dose change, H8)
  const [stoppedOn, setStoppedOn] = useState<string | null>(null);
  const [stopTried, setStopTried] = useState(false);
  const [stopReason, setStopReason] = useState("");

  if (patients.isPending || (own && meds.isPending)) return <LoadingView />;
  if (!own || !meds.data) {
    return (
      <RetryView
        text={errorText(patients.error ?? meds.error)}
        onRetry={() => void (patients.data ? meds.refetch() : patients.refetch())}
      />
    );
  }
  const med = meds.data.find((m) => m.id === id);
  if (!med) return <RetryView text={t("detail.notFound")} onRetry={() => void meds.refetch()} />;

  const failure = update.error ?? voidDose.error ?? remove.error;
  const voidedLabel = `✕ ${t("detail.voided")}`;
  const confirmDelete = () =>
    Alert.alert(t("detail.delete"), t("detail.deleteConfirm"), [
      { text: tc("cancel"), style: "cancel" },
      {
        text: t("detail.deleteYes"),
        style: "destructive",
        onPress: () => remove.mutate(undefined, { onSuccess: () => router.back() }),
      },
    ]);

  return (
    <Screen>
      <Title>{med.strength ? `${med.name} ${med.strength}` : med.name}</Title>
      {med.form && <Paragraph muted>{med.form}</Paragraph>}
      {med.stopped_on && (
        <Paragraph>{t("detail.stoppedText", { date: day(med.stopped_on) })}</Paragraph>
      )}
      {med.planned_end_on && !med.stopped_on && (
        <Paragraph>{t("detail.courseEnds", { date: day(med.planned_end_on) })}</Paragraph>
      )}
      <Paragraph muted>
        {med.reminders_enabled ? t("detail.reminderOn") : t("detail.reminderOff")}
      </Paragraph>
      {failure && <FormMessage kind="error" text={errorText(failure)} />}

      {med.is_current && (
        <Section title={t("detail.currentDose")}>
          <Paragraph>{regimenText(med.current_regimen)}</Paragraph>
          {med.current_regimen?.instructions && (
            <Paragraph muted>{med.current_regimen.instructions}</Paragraph>
          )}
          <Button
            label={t("detail.changeDose")}
            variant="secondary"
            onPress={() => router.push({ pathname: "/meds/[id]/dose", params: { id: med.id } })}
          />
        </Section>
      )}

      {med.next_regimen && (
        <Section title={t("detail.nextDose", { date: day(med.next_regimen.effective_from) })}>
          <Paragraph>{regimenText(med.next_regimen)}</Paragraph>
          <Button
            label={t("detail.voidNext")}
            variant="link"
            expanded={voiding}
            onPress={() => setVoiding(!voiding)}
          />
          {voiding && (
            <>
              <TextField
                label={t("detail.voidReason")}
                value={voidReason}
                maxLength={200}
                onChangeText={setVoidReason}
              />
              <Button
                label={t("detail.voidConfirm")}
                variant="danger"
                disabled={voidReason.trim() === ""}
                busy={voidDose.isPending}
                onPress={() =>
                  voidDose.mutate(
                    // biome-ignore lint/style/noNonNullAssertion: shown only with a next regimen
                    { regimenId: med.next_regimen!.id, reason: voidReason.trim() },
                    {
                      onSuccess: () => {
                        setVoiding(false);
                        setVoidReason("");
                      },
                    },
                  )
                }
              />
            </>
          )}
        </Section>
      )}

      <Section title={t("detail.history")}>
        {med.regimens.map((r) => (
          <View key={r.id} style={[styles.entry, { borderColor: p.border }]}>
            {r.voided_at && <Paragraph>{voidedLabel}</Paragraph>}
            <Text style={[styles.label, { color: p.text }]}>
              {t("detail.from", { date: day(r.effective_from) })}
            </Text>
            <Paragraph>{regimenText(r)}</Paragraph>
            {r.changed_by_note && <Paragraph muted>{r.changed_by_note}</Paragraph>}
          </View>
        ))}
      </Section>

      {med.is_current && (
        <Section title={t("detail.stopTitle")}>
          <Button
            label={t("detail.stop")}
            variant="secondary"
            expanded={stopping}
            onPress={() => setStopping(!stopping)}
          />
          {stopping && (
            <>
              <PickerField
                label={t("detail.stoppedOn")}
                mode="date"
                value={stoppedOn}
                maximum={new Date()}
                minimum={med.started_on ? new Date(`${med.started_on}T12:00:00`) : undefined}
                onChange={setStoppedOn}
                error={stopTried && stoppedOn === null ? t("form.errors.date") : undefined}
              />
              <Paragraph muted>{t("detail.stopNote")}</Paragraph>
              <TextField
                label={t("detail.stopReason")}
                value={stopReason}
                maxLength={200}
                onChangeText={setStopReason}
              />
              <Button
                label={t("detail.stopSave")}
                busy={update.isPending}
                onPress={() => {
                  setStopTried(true);
                  if (stoppedOn === null) return;
                  update.mutate(
                    fieldsOf(med, {
                      stopped_on: stoppedOn,
                      stop_reason: stopReason.trim() === "" ? null : stopReason.trim(),
                    }),
                    { onSuccess: () => setStopping(false) },
                  );
                }}
              />
            </>
          )}
        </Section>
      )}

      {own.access_level === "owner" && (
        <Button label={t("detail.delete")} variant="danger" onPress={confirmDelete} />
      )}
    </Screen>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  const p = usePalette();
  return (
    <View style={[styles.section, { backgroundColor: p.surface, borderColor: p.border }]}>
      <Text accessibilityRole="header" style={[styles.title, { color: p.text }]}>
        {title}
      </Text>
      {children}
    </View>
  );
}

const styles = StyleSheet.create({
  section: {
    gap: space.sm,
    padding: space.md,
    borderRadius: radius.md,
    borderWidth: StyleSheet.hairlineWidth * 2,
  },
  entry: { gap: space.xs, paddingTop: space.sm, borderTopWidth: StyleSheet.hairlineWidth * 2 },
  title: { fontSize: fontSize.bodyLarge, fontWeight: "700" },
  label: { fontSize: fontSize.body, fontWeight: "600" },
});
