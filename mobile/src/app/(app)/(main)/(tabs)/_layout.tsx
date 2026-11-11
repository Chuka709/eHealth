import { fontSize, space } from "@labtrack/shared";
import { Tabs } from "expo-router";
import { type ColorValue, StyleSheet, View } from "react-native";
import { useTranslations } from "use-intl";

import { Text } from "@/components/app-text";
import { Icon, type IconName } from "@/components/icon";
import { EmergencyButton } from "@/features/emergency/emergency-button";
import { NotificationsButton } from "@/features/notices/notifications-button";
import { usePalette } from "@/theme/use-palette";

/**
 * The main tabs: Нүүр · Эм · Тохиргоо. Each tab names itself in its header; the tab bar
 * reads its labels (the glyphs are decoration, hidden from screen readers).
 */
function HeaderTitle({ children, color }: { children: string; color: string }) {
  return (
    <Text
      accessibilityRole="header"
      numberOfLines={1}
      maxFontSizeMultiplier={1.3}
      style={{ color, fontSize: fontSize.bodyLarge, fontWeight: "600" }}
    >
      {children}
    </Text>
  );
}

function TabIcon({ name, color }: { name: IconName; color: ColorValue }) {
  const p = usePalette();
  // the navigator passes the tint as a string; anything else falls back to the muted tint
  return <Icon name={name} color={typeof color === "string" ? color : p.textMuted} size={26} />;
}

export default function TabsLayout() {
  const t = useTranslations("app");
  const p = usePalette();
  return (
    <Tabs
      screenOptions={{
        headerShown: true,
        // the app's palette (AA contrast), not the navigator's default blue/grey
        tabBarActiveTintColor: p.primary,
        tabBarInactiveTintColor: p.textMuted,
        tabBarStyle: { backgroundColor: p.surface, borderTopColor: p.border },
        sceneStyle: { backgroundColor: p.background },
        headerStyle: { backgroundColor: p.surface },
        headerTintColor: p.text,
        // one line, scaled to at most 1.3x: at 200% text the title crowded the header buttons
        headerTitle: ({ children }) => <HeaderTitle color={p.text}>{children}</HeaderTitle>,
      }}
    >
      <Tabs.Screen
        name="home"
        options={{
          title: t("name"),
          tabBarLabel: t("tabs.home"),
          // one tap from the app's first screen (docs/08, H17)
          headerRight: () => (
            <View style={styles.headerButtons}>
              <NotificationsButton />
              <EmergencyButton />
            </View>
          ),
          tabBarIcon: ({ color }) => <TabIcon name="home-variant-outline" color={color} />,
        }}
      />
      <Tabs.Screen
        name="meds"
        options={{
          title: t("meds.title"),
          tabBarLabel: t("tabs.meds"),
          tabBarIcon: ({ color }) => <TabIcon name="pill" color={color} />,
        }}
      />
      <Tabs.Screen
        name="profile"
        options={{
          title: t("health.title"),
          tabBarLabel: t("tabs.profile"),
          tabBarIcon: ({ color }) => <TabIcon name="heart-pulse" color={color} />,
        }}
      />
      <Tabs.Screen
        name="settings"
        options={{
          title: t("settings.title"),
          tabBarLabel: t("tabs.settings"),
          tabBarIcon: ({ color }) => <TabIcon name="cog-outline" color={color} />,
        }}
      />
    </Tabs>
  );
}

const styles = StyleSheet.create({
  headerButtons: { flexDirection: "row", alignItems: "center", gap: space.md },
});
