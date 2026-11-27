import { feedbackGlyph, fontSize, minTouchTarget, radius, space } from "@labtrack/shared";
import { Platform, Pressable, StyleSheet, View } from "react-native";
import { useTranslations } from "use-intl";
import { Text } from "@/components/app-text";
import { Spinner } from "@/components/spinner";
import { usePalette } from "@/theme/use-palette";
import { useHealth } from "./use-health";

/** `problemsOnly`: nothing while checking or connected - only an unreachable server shows. */
export function HealthStatus({ problemsOnly = false }: { problemsOnly?: boolean }) {
  const t = useTranslations("status");
  const p = usePalette();
  const { isPending, isError, refetch, isFetching } = useHealth();

  if (problemsOnly && !isError) return null;

  if (isPending) {
    return (
      <View style={styles.row} accessibilityRole="progressbar" accessibilityLabel={t("checking")}>
        <Spinner />
        <Text style={[styles.body, { color: p.textMuted }]}>{t("checking")}</Text>
      </View>
    );
  }

  const flag = isError ? p.feedback.error : p.feedback.success;
  const label = isError ? t("unreachable") : t("ok");
  return (
    <View style={{ gap: space.lg }}>
      <View
        style={[styles.badge, { backgroundColor: flag.bg }]}
        accessible
        accessibilityRole="text"
        accessibilityLabel={label}
        testID="health-badge"
      >
        {/* Colour + icon + text: status is never conveyed by colour alone. */}
        <Text style={[styles.glyph, { color: flag.fg }]} importantForAccessibility="no">
          {isError ? feedbackGlyph.error : feedbackGlyph.success}
        </Text>
        <Text style={[styles.body, { color: flag.fg, flexShrink: 1 }]}>{label}</Text>
      </View>
      {isError && (
        <Pressable
          onPress={() => refetch()}
          disabled={isFetching}
          accessibilityRole="button"
          accessibilityState={{ disabled: isFetching, busy: isFetching }}
          style={({ pressed }) => [
            styles.button,
            { backgroundColor: p.primary, opacity: pressed || isFetching ? 0.7 : 1 },
          ]}
        >
          <Text style={[styles.buttonText, { color: p.onPrimary }]}>{t("retry")}</Text>
        </Pressable>
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  row: { flexDirection: "row", alignItems: "center", gap: space.sm },
  badge: {
    flexDirection: "row",
    alignItems: "center",
    gap: space.sm,
    padding: space.md,
    borderRadius: radius.md,
  },
  glyph: { fontSize: fontSize.bodyLarge, fontWeight: "700" },
  body: { fontSize: fontSize.body, lineHeight: fontSize.body * 1.4 },
  button: {
    minHeight: Platform.OS === "ios" ? minTouchTarget.ios : minTouchTarget.android,
    borderRadius: radius.md,
    alignItems: "center",
    justifyContent: "center",
    paddingHorizontal: space.lg,
  },
  buttonText: { fontSize: fontSize.body, fontWeight: "600" },
});
