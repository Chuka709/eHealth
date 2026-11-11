import { fontSize, minTouchTarget, radius, space } from "@labtrack/shared";
import { ActivityIndicator, Platform, Pressable, StyleSheet } from "react-native";
import { Text } from "@/components/app-text";

import { usePalette } from "@/theme/use-palette";

interface ButtonProps {
  label: string;
  onPress: () => void;
  /**
   * primary: filled; secondary: outlined; danger: outlined in the danger colour (sign out,
   * delete); link: text only (same touch target).
   */
  variant?: "primary" | "secondary" | "danger" | "link";
  busy?: boolean;
  disabled?: boolean;
  /** Spoken label when it differs from the visible text (e.g. adds context). */
  accessibilityLabel?: string;
  /** For show/hide toggles: announced as expanded/collapsed (role button, not link). */
  expanded?: boolean;
  /** For one-of choices: announced as selected and marked with ✓ (not colour alone). */
  selected?: boolean;
  /** For several-of choices (week days): a checkbox, marked with ✓ when checked. */
  checked?: boolean;
}

export function Button({
  label,
  onPress,
  variant = "primary",
  busy = false,
  disabled = false,
  accessibilityLabel,
  expanded,
  selected,
  checked,
}: ButtonProps) {
  const p = usePalette();
  const inactive = disabled || busy;
  const filled = variant === "primary";
  const tone = variant === "danger" ? p.danger : p.primary;
  const role =
    checked !== undefined
      ? "checkbox"
      : selected !== undefined
        ? "radio"
        : variant === "link" && expanded === undefined
          ? "link"
          : "button";
  const marked = selected ?? checked;
  return (
    <Pressable
      onPress={onPress}
      disabled={inactive}
      accessibilityRole={role}
      accessibilityLabel={accessibilityLabel ?? label}
      accessibilityState={{ disabled: inactive, busy, expanded, selected, checked: marked }}
      style={({ pressed }) => [
        styles.button,
        filled && { backgroundColor: p.primary },
        (variant === "secondary" || variant === "danger") && {
          borderColor: tone,
          borderWidth: StyleSheet.hairlineWidth * 2,
        },
        // Busy stays fully legible (the label is still being read); only disabled is dimmed.
        { opacity: disabled ? 0.5 : pressed ? 0.85 : 1 },
      ]}
    >
      {busy && <ActivityIndicator color={filled ? p.onPrimary : tone} />}
      <Text style={[styles.label, { color: filled ? p.onPrimary : tone }]}>
        {marked ? `✓ ${label}` : label}
      </Text>
    </Pressable>
  );
}

const styles = StyleSheet.create({
  button: {
    minHeight: Platform.OS === "ios" ? minTouchTarget.ios : minTouchTarget.android,
    borderRadius: radius.md,
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "center",
    gap: space.sm,
    paddingHorizontal: space.lg,
    paddingVertical: space.sm,
  },
  label: { fontSize: fontSize.body, fontWeight: "600", textAlign: "center", flexShrink: 1 },
});
