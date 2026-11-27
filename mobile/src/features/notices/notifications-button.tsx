import { fontSize, minTouchTarget, space } from "@labtrack/shared";
import { useRouter } from "expo-router";
import { Platform, Pressable, StyleSheet } from "react-native";
import { useTranslations } from "use-intl";
import { Text } from "@/components/app-text";
import { Icon } from "@/components/icon";

import { usePalette } from "@/theme/use-palette";

import { unreadCount, useNotices } from "./use-notifications";

/** The bell in Home's header, with the number of unread notifications (icon + number; the
 * screen reader hears the label with the count). */
export function NotificationsButton() {
  const t = useTranslations("app.notifications");
  const router = useRouter();
  const p = usePalette();
  const notices = useNotices();
  const unread = unreadCount(notices.data);
  return (
    <Pressable
      onPress={() => router.push("/notifications")}
      accessibilityRole="button"
      accessibilityLabel={unread > 0 ? t("openUnread", { count: unread }) : t("open")}
      style={({ pressed }) => [styles.button, { opacity: pressed ? 0.85 : 1 }]}
      testID="notifications-open"
    >
      <Icon name={unread > 0 ? "bell-badge-outline" : "bell-outline"} color={p.text} />
      {unread > 0 && (
        <Text numberOfLines={1} style={[styles.label, { color: p.primary }]}>
          {unread > 99 ? "99+" : unread}
        </Text>
      )}
    </Pressable>
  );
}

const styles = StyleSheet.create({
  button: {
    minHeight: Platform.OS === "ios" ? minTouchTarget.ios : minTouchTarget.android,
    minWidth: Platform.OS === "ios" ? minTouchTarget.ios : minTouchTarget.android,
    flexDirection: "row",
    justifyContent: "center",
    alignItems: "center",
    gap: 2,
    paddingHorizontal: space.sm,
  },
  label: { fontSize: fontSize.body, fontWeight: "700" },
});
