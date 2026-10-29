import { useRouter } from "expo-router";
import { useTranslations } from "use-intl";

import { Button } from "@/components/button";
import { Screen } from "@/components/screen";
import { Paragraph, Title } from "@/components/text";

export default function WelcomeScreen() {
  const t = useTranslations("app.welcome");
  const router = useRouter();
  return (
    <Screen>
      <Title>{t("title")}</Title>
      <Paragraph>{t("body")}</Paragraph>
      <Button label={t("activate")} onPress={() => router.push("/activate")} />
      <Button variant="secondary" label={t("login")} onPress={() => router.push("/login")} />
    </Screen>
  );
}
