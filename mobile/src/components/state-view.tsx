import { radius, space } from "@labtrack/shared";
import { onlineManager } from "@tanstack/react-query";
import { useSyncExternalStore } from "react";
import { StyleSheet, View } from "react-native";
import { useTranslations } from "use-intl";

import { usePalette } from "@/theme/use-palette";

import { Button } from "./button";
import { FormMessage } from "./form-message";
import { Icon, type IconName } from "./icon";
import { SPINNER_LARGE, Spinner } from "./spinner";
import { Paragraph } from "./text";

const isOnline = () => onlineManager.isOnline();

/**
 * The app's one full-screen loading state (user request 2026.11.27: the same loader everywhere,
 * centred - it sat in the top corner of screens without a header): the Spinner in the middle,
 * the spoken words under it. Offline with nothing cached, a query waits (paused) until the
 * network is back: then it says so instead of spinning for ever, and loads by itself once online.
 */
export function LoadingView() {
  const t = useTranslations("app.common");
  const p = usePalette();
  const online = useSyncExternalStore(onlineManager.subscribe.bind(onlineManager), isOnline);
  return (
    <View
      accessibilityLiveRegion="polite"
      style={[styles.center, styles.gap, styles.middle, { backgroundColor: p.background }]}
    >
      {online ? (
        <Spinner size="large" />
      ) : (
        <Icon name="cloud-off-outline" color={p.textMuted} size={SPINNER_LARGE} />
      )}
      {/* the words are what is read out, once (ui review L7) */}
      <Paragraph muted centered>
        {t(online ? "loading" : "offlineWaiting")}
      </Paragraph>
    </View>
  );
}

/** The same loader inside a section of a screen (a card still loading): small, with its words. */
export function InlineLoading() {
  const t = useTranslations("app.common");
  return (
    <View accessibilityLiveRegion="polite" style={styles.inline}>
      <Spinner />
      <Paragraph muted>{t("loading")}</Paragraph>
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
  inline: { flexDirection: "row", alignItems: "center", gap: space.sm },
  gap: { gap: space.lg },
  empty: {
    alignItems: "center",
    gap: space.md,
    padding: space.lg,
    borderRadius: radius.lg,
    borderWidth: StyleSheet.hairlineWidth,
  },
});
