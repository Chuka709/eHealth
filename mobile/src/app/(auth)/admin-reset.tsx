import { useRouter } from "expo-router";
import { useState } from "react";
import { useTranslations } from "use-intl";

import { Button } from "@/components/button";
import { FormMessage } from "@/components/form-message";
import { Screen } from "@/components/screen";
import { Paragraph, Title } from "@/components/text";
import { acknowledgeAdminReset } from "@/features/auth/session";
import { CallSupportButton } from "@/features/auth/support-contact";
import { supportPhone } from "@/lib/support";

/**
 * Shown on a device whose session an admin reset revoked (docs/04 §1 step 5a): the victim of a
 * fraudulent reset learns about it here and is told whom to call. It survives an app restart
 * until the user moves on (session.ts `adminResetNotice`).
 */
export default function AdminResetScreen() {
  const t = useTranslations("app.adminReset");
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  return (
    <Screen>
      <Title>{t("title")}</Title>
      <Paragraph>{t("body")}</Paragraph>
      {/* Announced on open (FormMessage), so screen-reader users hear the call to action. */}
      <FormMessage
        kind="warning"
        text={supportPhone ? t("ifNotYou", { phone: supportPhone }) : t("ifNotYouNoPhone")}
      />
      <CallSupportButton variant="primary" />
      <Button
        variant="secondary"
        label={t("login")}
        busy={busy}
        onPress={() => {
          setBusy(true);
          void acknowledgeAdminReset().then(() => router.replace("/login"));
        }}
      />
    </Screen>
  );
}
