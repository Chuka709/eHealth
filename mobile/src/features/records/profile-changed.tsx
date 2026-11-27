import { useRouter } from "expo-router";
import { useTranslations } from "use-intl";

import { Button } from "@/components/button";
import { Screen } from "@/components/screen";
import { Paragraph } from "@/components/text";

/** A form whose profile changed while it was open: nothing is saved; the user starts again. */
export function ProfileChanged() {
  const t = useTranslations("app.profiles");
  const router = useRouter();
  return (
    <Screen>
      <Paragraph>{t("changed")}</Paragraph>
      <Button label={t("changedBack")} onPress={() => router.back()} />
    </Screen>
  );
}
