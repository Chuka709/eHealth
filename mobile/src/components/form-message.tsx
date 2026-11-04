import { feedbackGlyph, fontSize, radius, space } from "@labtrack/shared";
import { useEffect } from "react";
import { AccessibilityInfo, Platform, StyleSheet, Text, View } from "react-native";

import { usePalette } from "@/theme/use-palette";

/**
 * Error, warning or success notice: colour + glyph + text (never colour alone), in feedback
 * colours, never the clinical flag ones. Announced once when it appears or changes: iOS needs an
 * explicit announcement (live regions do nothing there), Android uses the live region.
 */
export function FormMessage({
  kind,
  text,
  quiet = false,
}: {
  kind: "error" | "warning" | "success";
  text: string;
  /** a standing notice (not a reaction to the user's action): read politely, never announced */
  quiet?: boolean;
}) {
  const p = usePalette();
  const colours = p.feedback[kind];
  useEffect(() => {
    if (Platform.OS === "ios" && !quiet) AccessibilityInfo.announceForAccessibility(text);
  }, [text, quiet]);
  return (
    <View
      accessible
      accessibilityRole={kind === "success" ? "text" : "alert"}
      accessibilityLiveRegion={kind === "success" || quiet ? "polite" : "assertive"}
      accessibilityLabel={text}
      style={[styles.box, { backgroundColor: colours.bg }]}
    >
      <Text importantForAccessibility="no" style={[styles.glyph, { color: colours.fg }]}>
        {feedbackGlyph[kind]}
      </Text>
      <Text selectable style={[styles.text, { color: colours.fg }]}>
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
