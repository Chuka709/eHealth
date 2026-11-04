import { fontSize, space } from "@labtrack/shared";
import { StyleSheet, Text, View } from "react-native";
import { useTranslations } from "use-intl";

import { Button } from "@/components/button";
import { Choices, MultiChoices, SelectList } from "@/components/choices";
import { PickerField } from "@/components/date-field";
import { TextField } from "@/components/text-field";
import { usePalette } from "@/theme/use-palette";

import {
  MAX_TIMES,
  type ScheduleDraft,
  type ScheduleErrors,
  timeRow,
  UNITS,
  WEEKDAYS,
} from "./med-draft";

/**
 * How often, at what times and how much - as the doctor instructed (a dose per time: 2 mg
 * at 08:00, 1.5 mg at 20:00). Nothing is suggested or filled in (CLAUDE.md rule 10).
 */
export function ScheduleEditor({
  value,
  onChange,
  errors,
}: {
  value: ScheduleDraft;
  onChange: (next: ScheduleDraft) => void;
  errors: ScheduleErrors | null;
}) {
  const t = useTranslations("app.meds");
  const p = usePalette();
  const set = (patch: Partial<ScheduleDraft>) => onChange({ ...value, ...patch });
  const unitName =
    value.unit === null
      ? null
      : value.unit === "other"
        ? value.unitText.trim() || null
        : t(`units.${value.unit}`);
  const amountLabel = (n: number) =>
    unitName ? t("form.amountUnit", { n, unit: unitName }) : t("form.amount", { n });
  const setRow = (key: string, patch: { at?: string; amount?: string }) =>
    set({ times: value.times.map((r) => (r.key === key ? { ...r, ...patch } : r)) });

  return (
    <View style={styles.group}>
      <Choices
        label={t("form.scheduleType")}
        options={["daily", "weekly", "prn"] as const}
        value={value.kind}
        labelOf={(k) => t(`form.${k}`)}
        onSelect={(kind) => set({ kind })}
      />
      <Text style={[styles.note, { color: p.textMuted }]}>{t("form.unsupported")}</Text>

      {value.kind === "weekly" && (
        <MultiChoices
          label={t("form.days")}
          options={WEEKDAYS}
          values={value.days}
          labelOf={(d) => t(`weekday.${d}`)}
          onToggle={(d) =>
            set({
              days: value.days.includes(d) ? value.days.filter((x) => x !== d) : [...value.days, d],
            })
          }
          error={errors?.days ? t("form.errors.days") : undefined}
        />
      )}

      <SelectList
        label={t("form.unit")}
        options={UNITS}
        value={value.unit}
        labelOf={(u) => t(`units.${u}`)}
        onSelect={(unit) => set({ unit })}
        error={errors?.unit ? t("form.errors.unit") : undefined}
      />
      {value.unit === "other" && (
        <TextField
          label={t("form.unitOther")}
          value={value.unitText}
          maxLength={200}
          error={errors?.unitOther ? t("form.errors.unitOther") : undefined}
          onChangeText={(unitText) => set({ unitText })}
        />
      )}
      {value.kind !== "prn" && (
        <View style={styles.group}>
          <Text style={[styles.label, { color: p.text }]} accessibilityRole="header">
            {t("form.times")}
          </Text>
          {value.times.map((row, index) => {
            const n = index + 1;
            return (
              <View key={row.key} style={[styles.row, { borderColor: p.border }]}>
                <PickerField
                  label={t("form.timeLabel", { n })}
                  mode="time"
                  value={row.at}
                  onChange={(at) => setRow(row.key, { at })}
                />
                <TextField
                  label={amountLabel(n)}
                  hint={t("form.amountHint")}
                  value={row.amount}
                  keyboardType="decimal-pad"
                  maxLength={10}
                  error={errors?.amounts?.[row.key] ? t("form.errors.amount") : undefined}
                  onChangeText={(amount) => setRow(row.key, { amount })}
                />
                {value.times.length > 1 && (
                  <Button
                    label={t("form.removeTime", { n })}
                    variant="link"
                    onPress={() => set({ times: value.times.filter((r) => r.key !== row.key) })}
                  />
                )}
              </View>
            );
          })}
          {errors?.times && <ErrorText text={t("form.errors.time")} />}
          {errors?.duplicate && <ErrorText text={t("form.errors.duplicate")} />}
          {errors?.amountAll && <ErrorText text={t("form.errors.amountAll")} />}
          {value.times.length < MAX_TIMES && (
            <Button
              label={t("form.addTime")}
              variant="secondary"
              onPress={() => set({ times: [...value.times, timeRow(nextTime(value))] })}
            />
          )}
        </View>
      )}

      {value.kind === "prn" && (
        <TextField
          label={amountLabel(1)}
          hint={t("form.amountHint")}
          value={value.prnAmount}
          keyboardType="decimal-pad"
          maxLength={10}
          error={errors?.amounts?.prn ? t("form.errors.amount") : undefined}
          onChangeText={(prnAmount) => set({ prnAmount })}
        />
      )}

      <TextField
        label={t("form.instructions")}
        hint={t("form.instructionsHint")}
        value={value.instructions}
        maxLength={4000}
        multiline
        onChangeText={(instructions) => set({ instructions })}
      />
    </View>
  );
}

/** A new row starts on the hour after the last one, never on a time already chosen. */
function nextTime(value: ScheduleDraft): string {
  const taken = new Set(value.times.map((r) => r.at));
  const last = value.times.at(-1)?.at ?? "07:00";
  let hour = Number(last.slice(0, 2));
  for (let i = 0; i < 24; i += 1) {
    hour = (hour + 1) % 24;
    const at = `${String(hour).padStart(2, "0")}:00`;
    if (!taken.has(at)) return at;
  }
  return "12:00";
}

function ErrorText({ text }: { text: string }) {
  const p = usePalette();
  return (
    <Text accessibilityLiveRegion="polite" style={[styles.note, { color: p.danger }]}>
      {text}
    </Text>
  );
}

const styles = StyleSheet.create({
  group: { gap: space.md },
  row: { gap: space.sm, paddingTop: space.sm, borderTopWidth: StyleSheet.hairlineWidth * 2 },
  label: { fontSize: fontSize.bodyLarge, fontWeight: "700" },
  note: { fontSize: fontSize.body, lineHeight: fontSize.body * 1.4 },
});
