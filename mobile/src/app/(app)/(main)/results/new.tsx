import { space } from "@labtrack/shared";
import { useLocalSearchParams, useRouter } from "expo-router";
import { useState } from "react";
import { StyleSheet, View } from "react-native";
import { useTranslations } from "use-intl";

import { Button } from "@/components/button";
import { Choices } from "@/components/choices";
import { PickerField } from "@/components/date-field";
import { FormMessage } from "@/components/form-message";
import { Screen } from "@/components/screen";
import { Paragraph, Title } from "@/components/text";
import { TextField } from "@/components/text-field";
import { useRecordProfile } from "@/features/health/record-screens";
import { localMoment } from "@/features/review/moments";
import { useCreateReport } from "@/features/review/use-review";
import { useErrorText } from "@/lib/use-error-text";

type Row = {
  key: number;
  name: string;
  value: string;
  unit: string;
  ref: string;
  critical: string;
};
type TextOf = Exclude<keyof Row, "key">;
let nextKey = 0;
const emptyRow = (): Row => ({
  key: nextKey++,
  name: "",
  value: "",
  unit: "",
  ref: "",
  critical: "",
});

/**
 * A result typed in by hand (Phase 5.4-5.5): from a paper result, or from a scan or photo that
 * is not read (Q50; `document` names it). It is a draft like a read one - checked, then
 * confirmed on the review screen. The date is always said, and a time only if printed (H30).
 */
export default function NewResultScreen() {
  const params = useLocalSearchParams<{ document?: string }>();
  const t = useTranslations("app.upload.review");
  const tu = useTranslations("app.upload");
  const errorText = useErrorText();
  const router = useRouter();
  const { own } = useRecordProfile();
  const create = useCreateReport(own?.id);
  const [lab, setLab] = useState("");
  const [day, setDay] = useState<string | null>(null);
  const [precision, setPrecision] = useState<"day" | "minute" | null>(null);
  const [time, setTime] = useState<string | null>(null);
  const [rows, setRows] = useState<Row[]>(() => [emptyRow()]);
  const [missing, setMissing] = useState(false);

  if (!own) {
    return (
      <Screen>
        <Paragraph>{tu("noProfile")}</Paragraph>
      </Screen>
    );
  }
  const set = (i: number, field: TextOf, text: string) =>
    setRows((all) => all.map((r, j) => (j === i ? { ...r, [field]: text } : r)));
  const filled = rows.filter((r) => r.name.trim() || r.value.trim());
  const dateOk = day !== null && precision !== null && (precision === "day" || time !== null);
  const rowsOk = filled.length > 0 && filled.every((r) => r.name.trim() && r.value.trim());

  const save = () => {
    if (!dateOk || !rowsOk || day === null || precision === null) {
      setMissing(true);
      return;
    }
    const opt = (text: string) => (text.trim() ? text.trim() : undefined);
    create.mutate(
      {
        ...(params.document ? { document_id: params.document } : {}),
        ...(lab.trim() ? { lab_name: lab.trim() } : {}),
        collected_at: localMoment(day, precision === "minute" ? time : null),
        collected_precision: precision,
        results: filled.map((r) => ({
          raw_name: r.name.trim(),
          raw_value: r.value.trim(),
          raw_unit: opt(r.unit),
          ref_text: opt(r.ref),
          critical_text: opt(r.critical),
        })),
      },
      { onSuccess: (report) => router.replace(`/results/${report.id}`) },
    );
  };

  return (
    <Screen testID="new-result">
      <Title>{t("newTitle")}</Title>
      <Paragraph muted>{t("newHint")}</Paragraph>
      <TextField label={t("lab")} value={lab} onChangeText={setLab} maxLength={200} />
      <PickerField
        label={t("dateTitle")}
        mode="date"
        value={day}
        maximum={new Date()}
        onChange={setDay}
        error={missing && day === null ? t("required") : undefined}
      />
      <Choices
        label={t("precision")}
        options={["day", "minute"] as const}
        value={precision}
        labelOf={(o) => (o === "day" ? t("precisionDay") : t("precisionMinute"))}
        onSelect={setPrecision}
      />
      {precision === "minute" && (
        <PickerField
          label={t("time")}
          mode="time"
          value={time}
          onChange={setTime}
          error={missing && time === null ? t("required") : undefined}
        />
      )}
      {rows.map((r, i) => (
        <View key={r.key} style={styles.row} testID={`new-row-${i}`}>
          <TextField
            label={t("name")}
            value={r.name}
            onChangeText={(x) => set(i, "name", x)}
            maxLength={200}
            error={missing && !r.name.trim() && r.value.trim() ? t("required") : undefined}
          />
          <TextField
            label={t("value")}
            value={r.value}
            onChangeText={(x) => set(i, "value", x)}
            maxLength={200}
            error={missing && !r.value.trim() && r.name.trim() ? t("required") : undefined}
          />
          <TextField
            label={t("unit")}
            value={r.unit}
            onChangeText={(x) => set(i, "unit", x)}
            maxLength={50}
          />
          <TextField
            label={t("ref")}
            value={r.ref}
            onChangeText={(x) => set(i, "ref", x)}
            maxLength={300}
          />
          <TextField
            label={t("criticalField")}
            value={r.critical}
            onChangeText={(x) => set(i, "critical", x)}
            maxLength={300}
          />
          {rows.length > 1 && (
            <Button
              label={t("removeRow")}
              variant="quiet"
              compact
              onPress={() => setRows((all) => all.filter((_, j) => j !== i))}
            />
          )}
        </View>
      ))}
      {rows.length < 100 && (
        <Button
          label={t("addAnother")}
          variant="secondary"
          onPress={() => setRows((all) => [...all, emptyRow()])}
        />
      )}
      {missing && filled.length === 0 && <FormMessage kind="error" text={t("required")} />}
      {create.error && <FormMessage kind="error" text={errorText(create.error)} />}
      <Button label={t("create")} busy={create.isPending} onPress={save} />
    </Screen>
  );
}

const styles = StyleSheet.create({ row: { gap: space.sm } });
