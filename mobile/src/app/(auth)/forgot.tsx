import { useTranslations } from "use-intl";

import { Screen } from "@/components/screen";
import { Paragraph, Title } from "@/components/text";
import { CallSupportButton } from "@/features/auth/support-contact";
import { supportPhone } from "@/lib/support";

/** Forgotten password: only an admin can issue a reset code (docs/04 §1 step 1). */
export default function ForgotScreen() {
  const t = useTranslations("app.forgot");
  return (
    <Screen>
      <Title>{t("title")}</Title>
      <Paragraph>{t("body")}</Paragraph>
      <Paragraph>{t("never")}</Paragraph>
      {supportPhone ? <CallSupportButton /> : <Paragraph>{t("noPhone")}</Paragraph>}
    </Screen>
  );
}
