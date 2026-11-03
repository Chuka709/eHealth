import { useState } from "react";
import { useTranslations } from "use-intl";

import { Button } from "@/components/button";
import { Screen } from "@/components/screen";
import { Title } from "@/components/text";
import { signOut } from "@/features/auth/session";
import { HealthStatus } from "@/features/status/health-status";

// Placeholder home until the Phase 1.11e profile/settings screens (sign-out moves there,
// with a confirmation).
export default function HomeScreen() {
  const t = useTranslations();
  const [busy, setBusy] = useState(false);
  return (
    <Screen>
      <Title>{t("status.title")}</Title>
      <HealthStatus />
      <Button
        variant="secondary"
        label={t("app.common.signOut")}
        busy={busy}
        onPress={() => {
          setBusy(true);
          void signOut().finally(() => setBusy(false));
        }}
      />
    </Screen>
  );
}
