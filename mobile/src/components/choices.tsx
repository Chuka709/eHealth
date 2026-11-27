import { fontSize, space } from "@labtrack/shared";
import { useState } from "react";
import { StyleSheet, View } from "react-native";
import { useTranslations } from "use-intl";
import { Text } from "@/components/app-text";

import { usePalette } from "@/theme/use-palette";

import { Button } from "./button";

/**
 * One-of choices as buttons: announced as radio buttons, the chosen one marked ✓ (not colour
 * alone). The question stays a readable text on both platforms (a container's label alone is
 * not read by VoiceOver).
 */
export function Choices<T extends string | number>({
  label,
  options,
  value,
  labelOf,
  onSelect,
  columns = 1,
}: {
  label: string;
  options: readonly T[];
  value: T | null;
  labelOf: (option: T) => string;
  onSelect: (option: T) => void;
  columns?: 1 | 2;
}) {
  const p = usePalette();
  return (
    <View style={styles.group} accessibilityRole="radiogroup" accessibilityLabel={label}>
      <Text style={[styles.label, { color: p.text }]}>{label}</Text>
      <View style={columns === 2 ? styles.grid : styles.choices}>
        {options.map((option) => (
          <View key={String(option)} style={columns === 2 ? styles.half : styles.full}>
            <Button
              label={labelOf(option)}
              variant="secondary"
              selected={value === option}
              onPress={() => onSelect(option)}
            />
          </View>
        ))}
      </View>
    </View>
  );
}

/** Several-of choices (week days): checkboxes marked ✓, two per row. */
export function MultiChoices<T extends string | number>({
  label,
  options,
  values,
  labelOf,
  onToggle,
  error,
  compact = false,
}: {
  label: string;
  options: readonly T[];
  values: readonly T[];
  labelOf: (option: T) => string;
  onToggle: (option: T) => void;
  error?: string;
  /** small chips that wrap onto as few lines as they need - filters above a list (UX audit
   * #11); wrapped, not scrolled sideways: every choice stays in sight (ui review M1) */
  compact?: boolean;
}) {
  const p = usePalette();
  if (compact) {
    return (
      <View style={styles.group}>
        <Text style={[styles.label, { color: p.text }]}>{label}</Text>
        <View style={styles.chips}>
          {options.map((option) => (
            <Button
              key={String(option)}
              compact
              label={labelOf(option)}
              variant="secondary"
              checked={values.includes(option)}
              onPress={() => onToggle(option)}
            />
          ))}
        </View>
      </View>
    );
  }
  return (
    <View style={styles.group}>
      <Text style={[styles.label, { color: p.text }]}>{label}</Text>
      <View style={styles.grid}>
        {options.map((option) => (
          <View key={String(option)} style={styles.half}>
            <Button
              label={labelOf(option)}
              variant="secondary"
              checked={values.includes(option)}
              onPress={() => onToggle(option)}
            />
          </View>
        ))}
      </View>
      {error && (
        <Text accessibilityLiveRegion="polite" style={[styles.error, { color: p.danger }]}>
          {error}
        </Text>
      )}
    </View>
  );
}

/**
 * A choice from a longer list: one button saying the field and its value ("Улс: Монгол");
 * pressing it opens the options as radio buttons, choosing one closes them. No native picker:
 * those announce no field name to TalkBack / VoiceOver.
 */
export function SelectList<T extends string | number>({
  label,
  options,
  value,
  labelOf,
  onSelect,
  testID,
  error,
}: {
  label: string;
  options: readonly T[];
  value: T | null;
  labelOf: (option: T) => string;
  onSelect: (option: T) => void;
  testID?: string;
  error?: string;
}) {
  const t = useTranslations("app.common");
  const p = usePalette();
  const [open, setOpen] = useState(false);
  const shown = value === null ? t("notSet") : labelOf(value);
  return (
    <View style={styles.group} testID={testID}>
      <Button
        label={t("choose", { label, value: shown })}
        variant="secondary"
        expanded={open}
        onPress={() => setOpen(!open)}
      />
      {open && (
        <Choices
          label={label}
          options={options}
          value={value}
          labelOf={labelOf}
          onSelect={(option) => {
            onSelect(option);
            setOpen(false);
          }}
        />
      )}
      {error && (
        <Text accessibilityLiveRegion="polite" style={[styles.error, { color: p.danger }]}>
          {error}
        </Text>
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  chips: { flexDirection: "row", flexWrap: "wrap", gap: space.sm },
  group: { gap: space.sm },
  choices: { gap: space.sm },
  grid: { flexDirection: "row", flexWrap: "wrap", gap: space.sm },
  full: { alignSelf: "stretch" },
  // two per row; each still a full-height touch target that grows with the font size
  half: { flexBasis: "47%", flexGrow: 1 },
  label: { fontSize: fontSize.body, fontWeight: "600" },
  error: { fontSize: fontSize.body },
});
