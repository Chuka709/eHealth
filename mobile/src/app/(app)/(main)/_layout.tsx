import { Stack } from "expo-router";
import { useTranslations } from "use-intl";

import { useEmergencyCardSync } from "@/features/emergency/use-card-sync";
import { useReminderResponses, useReminderSync } from "@/features/meds/use-reminders";
import { useZonePrompt } from "@/features/meds/use-zone-prompt";
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
  // local medicine reminders: planned, answered, and moved when the time zone changes
  useReminderSync();
  useReminderResponses();
  useZonePrompt();
  // the saved emergency card follows every change (the locked app and an offline phone show it)
  useEmergencyCardSync();
  return (
    <Stack screenOptions={{ headerBackTitle: t("common.back") }}>
      <Stack.Screen name="(tabs)" options={{ headerShown: false, title: t("name") }} />
      <Stack.Screen name="emergency" options={{ title: t("emergency.title") }} />
      <Stack.Screen name="settings/emergency" options={{ title: t("emergency.title") }} />
      <Stack.Screen
        name="settings/emergency-wallpaper"
        options={{ title: t("emergency.export.wallpaper") }}
      />
      <Stack.Screen
        name="settings/medical-id"
        options={{ title: t("emergency.export.medicalId") }}
      />
      <Stack.Screen name="settings/profile" options={{ title: t("profile.title") }} />
      <Stack.Screen name="settings/password" options={{ title: t("passwordChange.title") }} />
      <Stack.Screen name="settings/devices" options={{ title: t("devices.title") }} />
      <Stack.Screen name="settings/consents" options={{ title: t("consentSettings.title") }} />
      <Stack.Screen name="settings/admin-history" options={{ title: t("adminHistory.title") }} />
      <Stack.Screen name="settings/delete-account" options={{ title: t("deleteAccount.title") }} />
      <Stack.Screen name="transplants/index" options={{ title: t("transplant.listTitle") }} />
      <Stack.Screen name="transplants/new" options={{ title: t("transplant.add") }} />
      <Stack.Screen name="transplants/[id]" options={{ title: t("transplant.editTitle") }} />
      <Stack.Screen name="meds/new" options={{ title: t("meds.add") }} />
      <Stack.Screen name="events/index" options={{ title: t("health.events") }} />
      <Stack.Screen name="events/[id]" options={{ title: t("health.event.edit") }} />
      <Stack.Screen name="allergies/index" options={{ title: t("health.allergies") }} />
      <Stack.Screen name="allergies/[id]" options={{ title: t("health.allergy.edit") }} />
      <Stack.Screen name="contacts/index" options={{ title: t("health.contacts") }} />
      <Stack.Screen name="contacts/[id]" options={{ title: t("health.contact.edit") }} />
      <Stack.Screen name="appointments/index" options={{ title: t("health.appointments") }} />
      <Stack.Screen name="appointments/[id]" options={{ title: t("health.appointment.edit") }} />
      <Stack.Screen name="questions/index" options={{ title: t("health.questions") }} />
      <Stack.Screen name="questions/[id]" options={{ title: t("health.question.edit") }} />
      <Stack.Screen name="vitals/index" options={{ title: t("health.vitals") }} />
      <Stack.Screen name="vitals/new" options={{ title: t("health.vital.add") }} />
      <Stack.Screen name="settings/reminders" options={{ title: t("meds.reminders.title") }} />
      <Stack.Screen name="meds/[id]/index" options={{ title: t("meds.detail.title") }} />
      <Stack.Screen name="meds/[id]/dose" options={{ title: t("meds.change.title") }} />
    </Stack>
  );
}
