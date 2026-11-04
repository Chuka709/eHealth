import { Stack } from "expo-router";
import { useTranslations } from "use-intl";

import { useLocalData } from "@/features/offline/use-local-data";

/**
 * Every signed-in screen except onboarding lives in this group, so a new screen is behind the
 * consent/onboarding guard of (app)/_layout by default. Each screen names itself in the header
 * (read first by screen readers); the back button says "Back" in the app language.
 */
export default function MainLayout() {
  const t = useTranslations("app");
  // encrypted offline cache + queued writes: only past the consent guard, signed in, unlocked
  useLocalData();
  return (
    <Stack screenOptions={{ headerBackTitle: t("common.back") }}>
      <Stack.Screen name="home" options={{ title: t("name") }} />
      <Stack.Screen name="settings/index" options={{ title: t("settings.title") }} />
      <Stack.Screen name="settings/profile" options={{ title: t("profile.title") }} />
      <Stack.Screen name="settings/password" options={{ title: t("passwordChange.title") }} />
      <Stack.Screen name="settings/devices" options={{ title: t("devices.title") }} />
      <Stack.Screen name="settings/consents" options={{ title: t("consentSettings.title") }} />
      <Stack.Screen name="settings/admin-history" options={{ title: t("adminHistory.title") }} />
      <Stack.Screen name="settings/delete-account" options={{ title: t("deleteAccount.title") }} />
    </Stack>
  );
}
