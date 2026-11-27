import { radius, space } from "@labtrack/shared";
import { onlineManager } from "@tanstack/react-query";
import { useSyncExternalStore } from "react";
import { StyleSheet, View } from "react-native";
import { useTranslations } from "use-intl";

import { usePalette } from "@/theme/use-palette";

import { Button } from "./button";
import { FormMessage } from "./form-message";
import { Icon, type IconName } from "./icon";
import { Spinner } from "./spinner";
import { Paragraph } from "./text";

const isOnline = () => onlineManager.isOnline();

/**
 * Full-screen loading state with a spoken label, over grey placeholders of the list to come
 * (UX audit #10): the screen looks like itself at once, never empty. Offline with nothing
 * cached, a query waits (paused) until the network is back: then it says so instead of spinning
 * for ever (DEVICE_TEST 2026.11.27), and loads by itself once online.
 */
export function LoadingView() {
  const t = useTranslations("app.common");
  const p = usePalette();
  const online = useSyncExternalStore(onlineManager.subscribe.bind(onlineManager), isOnline);
  if (!online) {
    return (
      <View
        accessibilityLiveRegion="polite"
        style={[styles.center, styles.gap, styles.middle, { backgroundColor: p.background }]}
      >
        <Icon name="cloud-off-outline" color={p.textMuted} size={40} />
        <Paragraph muted>{t("offlineWaiting")}</Paragraph>
      </View>
    );
  }
  return (
    <View
      accessibilityLiveRegion="polite"
      style={[styles.top, styles.gap, { backgroundColor: p.background }]}
    >
      <View style={styles.row}>
        {/* the words below are what is read out, once (ui review L7) */}
        <Spinner size="large" />
        <Paragraph muted>{t("loading")}</Paragraph>
      </View>
      {[0, 1, 2].map((i) => (
        <View
          key={i}
          accessibilityElementsHidden
          importantForAccessibility="no-hide-descendants"
          style={[styles.placeholder, { backgroundColor: p.surface, borderColor: p.border }]}
        >
          <View style={[styles.barWide, { backgroundColor: p.border }]} />
          <View style={[styles.barShort, { backgroundColor: p.border }]} />
        </View>
      ))}
    </View>
  );
}

/** Nothing here yet: a glyph, what it means, and the way to add the first one (UX audit #10). */
export function EmptyState({
  icon,
  text,
  action,
}: {
  icon: IconName;
  text: string;
  action?: { label: string; onPress: () => void };
}) {
  const p = usePalette();
  return (
    <View style={[styles.empty, { backgroundColor: p.surface, borderColor: p.border }]}>
      <Icon name={icon} color={p.textMuted} size={32} />
      <Paragraph>{text}</Paragraph>
      {action && <Button label={action.label} variant="secondary" onPress={action.onPress} />}
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
  middle: { alignItems: "center" },
  top: { flex: 1, padding: space.lg },
  gap: { gap: space.lg },
  row: { flexDirection: "row", alignItems: "center", gap: space.sm },
  placeholder: {
    borderRadius: radius.lg,
    borderWidth: StyleSheet.hairlineWidth,
    padding: space.lg,
    gap: space.sm,
  },
  barWide: { height: space.md, width: "70%", borderRadius: radius.sm },
  barShort: { height: space.md, width: "40%", borderRadius: radius.sm },
  empty: {
    alignItems: "center",
    gap: space.md,
    padding: space.lg,
    borderRadius: radius.lg,
    borderWidth: StyleSheet.hairlineWidth,
  },
});
