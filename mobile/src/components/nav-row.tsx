import { fontSize, minTouchTarget, radius, space } from "@labtrack/shared";
import { Platform, Pressable, StyleSheet, Text, View } from "react-native";

import { usePalette } from "@/theme/use-palette";

/**
 * A settings row that opens another screen: whole row is one button (label + hint read
 * together), › marks navigation. Our own row rather than @expo/ui ListItem, whose screen-reader
 * role is undocumented and whose List scrolls by itself (it cannot sit inside a form screen).
 */
export function NavRow({
  label,
  hint,
  onPress,
  testID,
}: {
  label: string;
  hint?: string;
  onPress: () => void;
  testID?: string;
}) {
  const p = usePalette();
  return (
    <Pressable
      onPress={onPress}
      accessibilityRole="button"
      accessibilityLabel={hint ? `${label}. ${hint}` : label}
      testID={testID}
      style={({ pressed }) => [
        styles.row,
        { backgroundColor: p.surface, borderColor: p.border, opacity: pressed ? 0.85 : 1 },
      ]}
    >
      <View style={styles.text}>
        <Text style={[styles.label, { color: p.text }]}>{label}</Text>
        {hint && <Text style={[styles.hint, { color: p.textMuted }]}>{hint}</Text>}
      </View>
      <Text importantForAccessibility="no" style={[styles.chevron, { color: p.textMuted }]}>
        ›
      </Text>
    </Pressable>
  );
}

const styles = StyleSheet.create({
  row: {
    minHeight: Platform.OS === "ios" ? minTouchTarget.ios : minTouchTarget.android,
    flexDirection: "row",
    alignItems: "center",
    gap: space.md,
    paddingHorizontal: space.md,
    paddingVertical: space.sm,
    borderRadius: radius.md,
    borderWidth: StyleSheet.hairlineWidth * 2,
  },
  text: { flex: 1, gap: space.xs },
  label: { fontSize: fontSize.body, fontWeight: "600" },
  hint: { fontSize: fontSize.caption, lineHeight: fontSize.caption * 1.4 },
  chevron: { fontSize: fontSize.title },
});
