import { fontSize, minTouchTarget, radius, space } from "@labtrack/shared";
import { useRouter } from "expo-router";
import { Platform, Pressable, StyleSheet, View } from "react-native";
import { useTranslations } from "use-intl";

import { Text } from "@/components/app-text";
import { Icon } from "@/components/icon";
import { usePalette } from "@/theme/use-palette";

/** The emergency card in one tap from Home's header (docs/08, H17): a red pill with an icon
 * and text (never colour alone). */
export function EmergencyButton() {
  const e = useTranslations("app.emergency");
  const router = useRouter();
  const p = usePalette();
  const target = Platform.OS === "ios" ? minTouchTarget.ios : minTouchTarget.android;
  return (
    <Pressable
      onPress={() => router.push("/emergency")}
      accessibilityRole="button"
      accessibilityLabel={e("openLabel")}
      hitSlop={{ top: space.xs, bottom: space.xs }}
      style={({ pressed }) => [styles.hit, { minHeight: target, opacity: pressed ? 0.85 : 1 }]}
      testID="emergency-open"
    >
      <View style={[styles.pill, { backgroundColor: p.emergency.bg }]}>
        <Icon name="medical-bag" color={p.emergency.fg} size={18} />
        <Text
          numberOfLines={1}
          maxFontSizeMultiplier={1.3}
          style={[styles.label, { color: p.emergency.fg }]}
        >
          {e("open")}
        </Text>
      </View>
    </Pressable>
  );
}

const styles = StyleSheet.create({
  hit: { justifyContent: "center", paddingHorizontal: space.sm },
  pill: {
    flexDirection: "row",
    alignItems: "center",
    gap: space.xs,
    borderRadius: radius.pill,
    paddingHorizontal: space.md,
    paddingVertical: space.xs + 2,
  },
  label: { fontSize: fontSize.body, fontWeight: "600" },
});
