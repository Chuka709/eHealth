import { radius, space } from "@labtrack/shared";
import { StyleSheet, View } from "react-native";
import { useTranslations } from "use-intl";

import { Button } from "@/components/button";
import { FormMessage } from "@/components/form-message";
import { Paragraph, Title } from "@/components/text";
import { useOwnProfile } from "@/features/health/record-screens";
import { useBiometricState } from "@/features/lock/biometric";
import { usePalette } from "@/theme/use-palette";

import { useCardOffer, useSetCardUnlocked } from "./use-unlocked-card";

/**
 * The one-time offer on Home, after onboarding (H17): with the app's biometric lock on, the
 * card would be locked away in an emergency. The risk is said before the choice; either answer
 * ends the offer; Settings can change it later. Off unless the user says yes (decision 10e).
 */
export function EmergencyCardOffer() {
  const e = useTranslations("app.emergency.unlocked");
  const p = usePalette();
  const { own } = useOwnProfile();
  const biometric = useBiometricState();
  const offer = useCardOffer();
  const setUnlocked = useSetCardUnlocked();
  if (!own || biometric.data?.choice !== "on" || !offer.show) return null;
  // the offer closes only once the choice is stored: a failed save is said, never lost
  const answer = async (on: boolean) => {
    try {
      // the last answer wins: "Not now" after a half-saved "Turn on" turns it off again
      await setUnlocked.mutateAsync({ patientId: own.id, on });
      await offer.answer.mutateAsync();
    } catch {
      // shown below; the offer stays
    }
  };
  const busy = setUnlocked.isPending || offer.answer.isPending;
  return (
    <View
      style={[styles.box, { borderColor: p.border, backgroundColor: p.surface }]}
      testID="emergency-offer"
    >
      <Title>{e("offerTitle")}</Title>
      <Paragraph>{e("body")}</Paragraph>
      <Paragraph>{e("risk")}</Paragraph>
      {(setUnlocked.isError || offer.answer.isError) && (
        <FormMessage kind="error" text={e("failed")} />
      )}
      {/* equal weight: neither answer is pushed */}
      <Button
        variant="secondary"
        label={e("offerYes")}
        busy={setUnlocked.isPending}
        disabled={busy}
        onPress={() => void answer(true)}
      />
      <Button
        variant="secondary"
        label={e("offerNo")}
        disabled={busy}
        onPress={() => void answer(false)}
      />
      <Paragraph muted>{e("offerLater")}</Paragraph>
    </View>
  );
}

const styles = StyleSheet.create({
  box: {
    borderWidth: StyleSheet.hairlineWidth * 2,
    borderRadius: radius.md,
    padding: space.lg,
    gap: space.md,
  },
});
