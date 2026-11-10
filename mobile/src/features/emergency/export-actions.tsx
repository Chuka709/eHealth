import { useRouter } from "expo-router";
import { useState } from "react";
import { useTranslations } from "use-intl";

import { Button } from "@/components/button";
import { FormMessage } from "@/components/form-message";
import { NavRow } from "@/components/nav-row";

import type { EmergencyCard } from "./snapshot";
import { shareWalletCard } from "./wallet-card";

/**
 * What can be made from the card for when the app cannot be opened (H17): the wallet card
 * (PDF), the lock-screen wallpaper and the phone's own Medical ID. Shown with the card on the
 * signed-in screens, never on the lock screen.
 */
export function EmergencyExports({ card }: { card: EmergencyCard }) {
  const x = useTranslations("app.emergency.export");
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const [problem, setProblem] = useState<"failed" | "unavailable" | null>(null);
  const wallet = async () => {
    setBusy(true);
    setProblem(null);
    try {
      if ((await shareWalletCard(card)) === "unavailable") setProblem("unavailable");
    } catch {
      setProblem("failed");
    } finally {
      setBusy(false);
    }
  };
  return (
    <>
      <Button
        variant="secondary"
        label={x("wallet")}
        accessibilityLabel={x("walletLabel")}
        busy={busy}
        onPress={() => void wallet()}
      />
      {problem && <FormMessage kind="error" text={x(problem)} />}
      <NavRow
        label={x("wallpaper")}
        hint={x("wallpaperHint")}
        onPress={() => router.push("/settings/emergency-wallpaper")}
        testID="emergency-wallpaper"
      />
      <NavRow
        label={x("medicalId")}
        hint={x("medicalIdHint")}
        onPress={() => router.push("/settings/medical-id")}
        testID="emergency-medical-id"
      />
    </>
  );
}
