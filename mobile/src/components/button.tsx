import { fontSize, minTouchTarget, radius, space } from "@labtrack/shared";
import { ActivityIndicator, Platform, Pressable, StyleSheet, Text } from "react-native";

import { usePalette } from "@/theme/use-palette";

interface ButtonProps {
  label: string;
  onPress: () => void;
  /** primary: filled; secondary: outlined; link: text only (same touch target). */
  variant?: "primary" | "secondary" | "link";
  busy?: boolean;
  disabled?: boolean;
  /** Spoken label when it differs from the visible text (e.g. adds context). */
  accessibilityLabel?: string;
}

export function Button({
  label,
  onPress,
  variant = "primary",
  busy = false,
  disabled = false,
  accessibilityLabel,
}: ButtonProps) {
  const p = usePalette();
  const inactive = disabled || busy;
  const filled = variant === "primary";
  return (
    <Pressable
      onPress={onPress}
      disabled={inactive}
      accessibilityRole={variant === "link" ? "link" : "button"}
      accessibilityLabel={accessibilityLabel ?? label}
      accessibilityState={{ disabled: inactive, busy }}
      style={({ pressed }) => [
        styles.button,
        filled && { backgroundColor: p.primary },
        variant === "secondary" && {
          borderColor: p.primary,
          borderWidth: StyleSheet.hairlineWidth * 2,
        },
        // Busy stays fully legible (the label is still being read); only disabled is dimmed.
        { opacity: disabled ? 0.5 : pressed ? 0.85 : 1 },
      ]}
    >
      {busy && <ActivityIndicator color={filled ? p.onPrimary : p.primary} />}
      <Text style={[styles.label, { color: filled ? p.onPrimary : p.primary }]}>{label}</Text>
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
