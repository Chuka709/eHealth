import { flagGlyph, fontSize, radius, space } from "@labtrack/shared";
import { useEffect } from "react";
import { AccessibilityInfo, StyleSheet, Text, View } from "react-native";

import { usePalette } from "@/theme/use-palette";

/**
 * Error, warning or success notice: colour + glyph + text (never colour alone). Announced to
 * screen readers when it appears or changes (live regions alone do nothing on iOS).
 */
export function FormMessage({
  kind,
  text,
}: {
  kind: "error" | "warning" | "success";
  text: string;
}) {
  const p = usePalette();
  const flag =
    kind === "success" ? p.flag.normal : kind === "warning" ? p.flag.high : p.flag.critical;
  const glyph = kind === "success" ? flagGlyph.normal : flagGlyph.critical;
  useEffect(() => {
    AccessibilityInfo.announceForAccessibility(text);
  }, [text]);
  return (
    <View
      accessible
      accessibilityRole={kind === "success" ? "text" : "alert"}
      accessibilityLabel={text}
      style={[styles.box, { backgroundColor: flag.bg }]}
    >
      <Text importantForAccessibility="no" style={[styles.glyph, { color: flag.fg }]}>
        {glyph}
      </Text>
      <Text selectable style={[styles.text, { color: flag.fg }]}>
        {text}
      </Text>
    </View>
  );
}

const styles = StyleSheet.create({
  box: {
    flexDirection: "row",
    alignItems: "flex-start",
    gap: space.sm,
    padding: space.md,
    borderRadius: radius.md,
  },
  glyph: { fontSize: fontSize.bodyLarge, fontWeight: "700" },
  text: { fontSize: fontSize.body, lineHeight: fontSize.body * 1.4, flexShrink: 1 },
});
