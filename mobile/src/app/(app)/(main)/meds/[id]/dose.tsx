import { fontSize } from "@labtrack/shared";
import { useLocalSearchParams, useRouter } from "expo-router";
import { useRef, useState } from "react";
import { StyleSheet, Text } from "react-native";
import { useTranslations } from "use-intl";
import { Button } from "@/components/button";
import { PickerField } from "@/components/date-field";
import { FormMessage } from "@/components/form-message";
import { Screen, type ScreenScroll } from "@/components/screen";
import { LoadingView, RetryView } from "@/components/state-view";
import { TextField } from "@/components/text-field";
import {
  draftFromSchedule,
  hasErrors,
  regimenBody,
  type ScheduleDraft,
  scheduleErrors,
} from "@/features/meds/med-draft";
import { ScheduleEditor } from "@/features/meds/schedule-editor";
import { useChangeDose, useMedications } from "@/features/meds/use-medications";
import { useActiveProfile } from "@/features/records/active-profile";
import { ProfileBanner } from "@/features/records/profile-banner";
import { usePatients } from "@/features/records/use-profile";
import { newClientId } from "@/lib/random";
import { useErrorText } from "@/lib/use-error-text";
import { usePalette } from "@/theme/use-palette";

const YEAR_MS = 365 * 24 * 60 * 60_000;

/**
 * A dose change: the new dose and schedule from a date the user picks (H8 - the date is
 * always asked). It is a new history row; the old dose stays as it was.
 */
export default function ChangeDoseScreen() {
  const t = useTranslations("app.meds");
  const router = useRouter();
  const errorText = useErrorText();
  const { id } = useLocalSearchParams<{ id: string }>();
  const patients = usePatients();
  const own = useActiveProfile(patients.data);
  const meds = useMedications(own?.id);
  const med = meds.data?.find((m) => m.id === id);

  if (patients.isPending || (own && meds.isPending)) return <LoadingView />;
  if (!own || !med) {
    return (
      <RetryView
        text={med === undefined && meds.data ? t("detail.notFound") : errorText(meds.error)}
        onRetry={() => void meds.refetch()}
      />
    );
  }
  const base = med.current_regimen;
  const start = base
    ? draftFromSchedule(
        base.schedule,
        base.dose_unit,
        base.dose_unit_text,
        base.dose_amount,
        base.instructions,
      )
    : null;
  return (
    <DoseForm
      patientId={own.id}
      medicationId={med.id}
      start={start}
      onDone={() => router.back()}
      errorText={errorText}
    />
  );
}

function DoseForm({
  patientId,
  medicationId,
  start,
  onDone,
  errorText,
}: {
  patientId: string;
  medicationId: string;
  start: ScheduleDraft | null;
  onDone: () => void;
  errorText: (e: unknown) => string;
}) {
  const t = useTranslations("app.meds");
  const p = usePalette();
  const scroll = useRef<ScreenScroll>(null);
  const change = useChangeDose(patientId, medicationId);
  const [schedule, setSchedule] = useState<ScheduleDraft>(
    () => start ?? draftFromSchedule({ type: "daily", times: [] }, null, null, null, null),
  );
  // never preset: a change always says from when (H8)
  const [from, setFrom] = useState<string | null>(null);
  const [note, setNote] = useState("");
  const [showErrors, setShowErrors] = useState(false);
  const sent = useRef<{ key: string; id: string } | null>(null);
  const errors = scheduleErrors(schedule);
  const invalid = hasErrors(errors) || from === null;

  const save = () => {
    setShowErrors(true);
    if (invalid || from === null) {
      scroll.current?.scrollTo({ y: 0, animated: true });
      return;
    }
    const key = JSON.stringify([schedule, from, note]);
    if (sent.current?.key !== key) sent.current = { key, id: newClientId() };
    change.mutate(regimenBody(schedule, sent.current.id, from, note), { onSuccess: onDone });
  };

  return (
    <Screen scrollRef={scroll}>
      <ProfileBanner />
      <Text style={[styles.note, { color: p.text }]}>{t("change.latest")}</Text>
      <Text style={[styles.note, { color: p.textMuted }]}>{t("form.disclaimer")}</Text>
      {showErrors && invalid && <FormMessage kind="error" text={t("form.errors.summary")} />}
      {change.error && <FormMessage kind="error" text={errorText(change.error)} />}
      <PickerField
        label={t("change.effectiveFrom")}
        mode="date"
        value={from}
        minimum={new Date(1950, 0, 1)}
        maximum={new Date(Date.now() + YEAR_MS)}
        onChange={setFrom}
        error={showErrors && from === null ? t("form.errors.date") : undefined}
      />
      <ScheduleEditor value={schedule} onChange={setSchedule} errors={showErrors ? errors : null} />
      <TextField label={t("change.note")} value={note} maxLength={4000} onChangeText={setNote} />
      <Button label={t("form.save")} busy={change.isPending} onPress={save} />
    </Screen>
  );
}

const styles = StyleSheet.create({
  note: { fontSize: fontSize.body, lineHeight: fontSize.body * 1.4 },
});
