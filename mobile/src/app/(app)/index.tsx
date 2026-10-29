import { fontSize, space } from "@labtrack/shared";
import { ScrollView, StyleSheet, Text } from "react-native";
import { useTranslations } from "use-intl";

import { HealthStatus } from "@/features/status/health-status";
import { usePalette } from "@/theme/use-palette";

export default function HomeScreen() {
  const t = useTranslations("status");
  const p = usePalette();
  return (
    <ScrollView
      contentInsetAdjustmentBehavior="automatic"
      style={{ backgroundColor: p.background }}
      contentContainerStyle={styles.content}
    >
      <Text accessibilityRole="header" style={[styles.title, { color: p.text }]}>
        {t("title")}
      </Text>
      <HealthStatus />
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  content: { padding: space.lg, gap: space.lg },
  title: { fontSize: fontSize.title, fontWeight: "700" },
});
