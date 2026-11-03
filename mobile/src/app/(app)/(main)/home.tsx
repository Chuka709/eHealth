import { useRouter } from "expo-router";
import { useTranslations } from "use-intl";

import { Button } from "@/components/button";
import { Screen } from "@/components/screen";
import { Title } from "@/components/text";
import { useMe } from "@/features/me/use-me";
import { HealthStatus } from "@/features/status/health-status";

// Placeholder home until Phase 2 (transplant, medicines). Loading /me applies the language.
export default function HomeScreen() {
  const t = useTranslations();
  const router = useRouter();
  useMe();
  return (
    <Screen>
      <Title>{t("status.title")}</Title>
      <HealthStatus />
      <Button
        variant="secondary"
        label={t("app.settings.open")}
        onPress={() => router.push("/settings")}
      />
    </Screen>
  );
}
