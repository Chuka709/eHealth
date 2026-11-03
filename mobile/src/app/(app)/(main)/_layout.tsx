import { Stack } from "expo-router";
import { useTranslations } from "use-intl";

/**
 * Every signed-in screen except onboarding lives in this group, so a new screen is behind the
 * consent/onboarding guard of (app)/_layout by default.
 */
export default function MainLayout() {
  const t = useTranslations("app");
  return <Stack screenOptions={{ headerTitle: t("name") }} />;
}
