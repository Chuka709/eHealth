import { space } from "@labtrack/shared";
import { ActivityIndicator, StyleSheet, View } from "react-native";
import { useTranslations } from "use-intl";

import { usePalette } from "@/theme/use-palette";

import { Button } from "./button";
import { FormMessage } from "./form-message";
import { Paragraph } from "./text";

/** Full-screen loading state with a spoken label. */
export function LoadingView() {
  const t = useTranslations("app.common");
  const p = usePalette();
  return (
    <View
      accessibilityLiveRegion="polite"
      style={[styles.center, styles.gap, { backgroundColor: p.background }]}
    >
      <ActivityIndicator color={p.primary} accessibilityLabel={t("loading")} />
      <Paragraph muted>{t("loading")}</Paragraph>
    </View>
  );
}

/** Full-screen error with a retry button (text from `useErrorText`). */
export function RetryView({ text, onRetry }: { text: string; onRetry: () => void }) {
  const t = useTranslations("status");
  const p = usePalette();
  return (
    <View style={[styles.center, styles.gap, { backgroundColor: p.background }]}>
      <FormMessage kind="error" text={text} />
      <Button label={t("retry")} onPress={onRetry} />
    </View>
  );
}

const styles = StyleSheet.create({
  center: { flex: 1, justifyContent: "center", padding: space.lg },
  gap: { gap: space.lg },
});
