import { fontSize, space } from "@labtrack/shared";
import { Tabs } from "expo-router";
import { type ColorValue, StyleSheet, Text, View } from "react-native";
import { useTranslations } from "use-intl";

import { EmergencyButton } from "@/features/emergency/emergency-button";
import { NotificationsButton } from "@/features/notices/notifications-button";
import { usePalette } from "@/theme/use-palette";

/**
 * The main tabs: Нүүр · Эм · Тохиргоо. Each tab names itself in its header; the tab bar
 * reads its labels (the glyphs are decoration, hidden from screen readers).
 */
function TabIcon({ glyph, color }: { glyph: string; color: ColorValue }) {
  return (
    <Text
      importantForAccessibility="no"
      accessible={false}
      style={{ color, fontSize: fontSize.title }}
    >
      {glyph}
    </Text>
  );
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
        headerStyle: { backgroundColor: p.surface },
        headerTintColor: p.text,
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
          tabBarIcon: ({ color }) => <TabIcon glyph="⌂" color={color} />,
        }}
      />
      <Tabs.Screen
        name="meds"
        options={{
          title: t("meds.title"),
          tabBarLabel: t("tabs.meds"),
          tabBarIcon: ({ color }) => <TabIcon glyph="℞" color={color} />,
        }}
      />
      <Tabs.Screen
        name="profile"
        options={{
          title: t("health.title"),
          tabBarLabel: t("tabs.profile"),
          tabBarIcon: ({ color }) => <TabIcon glyph="♥" color={color} />,
        }}
      />
      <Tabs.Screen
        name="settings"
        options={{
          title: t("settings.title"),
          tabBarLabel: t("tabs.settings"),
          tabBarIcon: ({ color }) => <TabIcon glyph="⚙" color={color} />,
        }}
      />
    </Tabs>
  );
}

const styles = StyleSheet.create({
  headerButtons: { flexDirection: "row", alignItems: "center", gap: space.md },
});
