import { fontSize, minTouchTarget, space } from "@labtrack/shared";
import { useRouter } from "expo-router";
import { Platform, Pressable, StyleSheet, Text } from "react-native";
import { useTranslations } from "use-intl";

import { usePalette } from "@/theme/use-palette";

/** 🆘 in Home's header: the emergency card in one tap (docs/08, H17). Glyph + text, in the
 * danger colour (never colour alone). */
export function EmergencyButton() {
  const e = useTranslations("app.emergency");
  const router = useRouter();
  const p = usePalette();
  return (
    <Pressable
      onPress={() => router.push("/emergency")}
      accessibilityRole="button"
      accessibilityLabel={e("openLabel")}
      hitSlop={space.sm}
      style={({ pressed }) => [styles.button, { opacity: pressed ? 0.85 : 1 }]}
      testID="emergency-open"
    >
      <Text style={[styles.label, { color: p.danger }]}>{e("open")}</Text>
    </Pressable>
  );
}

const styles = StyleSheet.create({
  button: {
    minHeight: Platform.OS === "ios" ? minTouchTarget.ios : minTouchTarget.android,
    minWidth: Platform.OS === "ios" ? minTouchTarget.ios : minTouchTarget.android,
    justifyContent: "center",
    paddingHorizontal: space.md,
  },
  label: { fontSize: fontSize.body, fontWeight: "700" },
});
