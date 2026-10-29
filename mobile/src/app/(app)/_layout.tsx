import { Stack } from "expo-router";
import { useTranslations } from "use-intl";

export default function AppLayout() {
  const t = useTranslations("app");
  return <Stack screenOptions={{ headerTitle: t("name") }} />;
}
