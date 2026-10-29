import { fontSize, radius, space } from "@labtrack/shared";
import { StyleSheet, Text, View } from "react-native";
import { useTranslations } from "use-intl";

import { usePalette } from "@/theme/use-palette";

const levelKeys = ["level0", "level1", "level2", "level3", "level4"] as const;

/**
 * Password strength: filled segments + text label. Advisory only (the server decides).
 * Uses the brand colour, not the clinical flag palette, so it never reads as a result flag.
 */
export function StrengthMeter({ score }: { score: 0 | 1 | 2 | 3 | 4 }) {
  const t = useTranslations("app.strength");
  const p = usePalette();
  const label = t("label", { level: t(levelKeys[score]) });
  return (
    <View accessible accessibilityRole="text" accessibilityLabel={label} style={styles.wrap}>
      <View style={styles.bar}>
        {[1, 2, 3, 4].map((segment) => (
          <View
            key={segment}
            style={[styles.segment, { backgroundColor: segment <= score ? p.primary : p.border }]}
          />
        ))}
      </View>
      <Text style={[styles.text, { color: p.textMuted }]}>{label}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: { gap: space.xs },
  bar: { flexDirection: "row", gap: space.xs },
  segment: { flex: 1, height: space.sm, borderRadius: radius.sm },
  text: { fontSize: fontSize.caption },
});
