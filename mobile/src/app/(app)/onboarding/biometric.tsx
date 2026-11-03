import { useState } from "react";
import { useTranslations } from "use-intl";

import { Button } from "@/components/button";
import { FormMessage } from "@/components/form-message";
import { Screen } from "@/components/screen";
import { Paragraph, Title } from "@/components/text";
import { authenticate, LOCK_AFTER_MINUTES, setBiometricChoice } from "@/features/lock/biometric";

/** One-time offer after the first consents (docs/04 §1 "Биометр түгжээ"). */
export default function BiometricOfferScreen() {
  const t = useTranslations("app.biometric");
  const [busy, setBusy] = useState(false);
  const [failed, setFailed] = useState(false);
  return (
    <Screen>
      <Title>{t("title")}</Title>
      <Paragraph>{t("body", { minutes: LOCK_AFTER_MINUTES })}</Paragraph>
      {failed && <FormMessage kind="error" text={t("failed")} />}
      <Button
        label={t("enable")}
        busy={busy}
        onPress={() => {
          setBusy(true);
          setFailed(false);
          void authenticate(t("prompt"), t("skip"))
            .then((ok) => (ok ? setBiometricChoice("on") : setFailed(true)))
            .catch(() => setFailed(true))
            .finally(() => setBusy(false));
        }}
      />
      <Button
        variant="secondary"
        label={t("skip")}
        disabled={busy}
        onPress={() => void setBiometricChoice("off").catch(() => setFailed(true))}
      />
      <Paragraph muted>{t("later")}</Paragraph>
    </Screen>
  );
}
