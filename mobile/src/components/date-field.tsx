import DateTimePicker from "@expo/ui/community/datetime-picker";
import { fontSize } from "@labtrack/shared";
import { useState } from "react";
import { Platform, StyleSheet, View } from "react-native";
import { useTranslations } from "use-intl";
import { Text } from "@/components/app-text";

import { formatDate } from "@/lib/dates";
import { usePalette } from "@/theme/use-palette";

import { Button } from "./button";

const pad = (n: number) => String(n).padStart(2, "0");

/** A calendar day as YYYY-MM-DD from a picker's local date. */
export function dayOf(date: Date): string {
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}`;
}

/** "HH:MM" from a picker's local time. */
export function hhmmOf(date: Date): string {
  return `${pad(date.getHours())}:${pad(date.getMinutes())}`;
}

/**
 * One button saying the field and its value ("Эхэлсэн өдөр: 2026.11.04"); pressing it opens
 * the platform date or time picker (Android: a dialog; iOS: inline until "Done").
 */
export function PickerField({
  label,
  mode,
  value,
  onChange,
  minimum,
  maximum,
  emptyText,
  accessibilityLabel,
  error,
}: {
  label: string;
  mode: "date" | "time";
  value: string | null; // YYYY-MM-DD or HH:MM
  onChange: (value: string) => void;
  minimum?: Date;
  maximum?: Date;
  emptyText?: string;
  accessibilityLabel?: string;
  error?: string;
}) {
  const t = useTranslations("app.common");
  const tm = useTranslations("app.meds.form");
  const p = usePalette();
  const [open, setOpen] = useState(false);
  const shown =
    value === null
      ? (emptyText ?? t("notSet"))
      : mode === "date"
        ? formatDate(`${value}T12:00:00Z`)
        : value;
  const current =
    value === null
      ? new Date()
      : mode === "date"
        ? new Date(`${value}T12:00:00`)
        : new Date(2000, 0, 1, Number(value.slice(0, 2)), Number(value.slice(3, 5)));
  return (
    <View>
      <Button
        label={t("choose", { label, value: shown })}
        accessibilityLabel={accessibilityLabel}
        variant="secondary"
        expanded={open}
        onPress={() => setOpen(!open)}
      />
      {open && (
        <DateTimePicker
          value={current}
          mode={mode}
          presentation="dialog"
          minimumDate={minimum}
          maximumDate={maximum}
          onValueChange={(_, date) => {
            onChange(mode === "date" ? dayOf(date) : hhmmOf(date));
            if (Platform.OS === "android") setOpen(false);
          }}
          onDismiss={() => setOpen(false)}
        />
      )}
      {error && (
        <Text accessibilityLiveRegion="polite" style={[styles.error, { color: p.danger }]}>
          {error}
        </Text>
      )}
      {open && Platform.OS === "ios" && (
        <Button label={tm("done")} onPress={() => setOpen(false)} />
      )}
    </View>
  );
}

const styles = StyleSheet.create({ error: { fontSize: fontSize.body } });
