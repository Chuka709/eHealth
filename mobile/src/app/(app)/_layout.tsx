import { Stack } from "expo-router";

import { LoadingView, RetryView } from "@/components/state-view";
import { needsConsent, useConsents } from "@/features/consents/use-consents";
import { useBiometricState } from "@/features/lock/biometric";
import { useErrorText } from "@/lib/use-error-text";

/**
 * Signed-in area. Until the required consents are given for the current text versions, the
 * consents screen is the only one; then the one-time biometric offer; then the app, whose
 * screens all live in (main) so new ones are guarded by default. The server enforces consents
 * on PHI routes from Phase 2 (`consents.require`); this guard is the user-facing part.
 */
export default function AppLayout() {
  const errorText = useErrorText();
  const consents = useConsents();
  const biometric = useBiometricState();

  if (consents.isPending || biometric.isPending) return <LoadingView />;
  // Fail closed without known consent state; a failed background refresh keeps the last one.
  if (!consents.data) {
    return <RetryView text={errorText(consents.error)} onRetry={() => void consents.refetch()} />;
  }
  const mustConsent = needsConsent(consents.data);
  const offerBiometric =
    !mustConsent && biometric.data?.available === true && biometric.data.choice === null;
  const ready = !mustConsent && !offerBiometric;

  return (
    <Stack screenOptions={{ headerShown: false }}>
      <Stack.Protected guard={mustConsent}>
        <Stack.Screen name="onboarding/consents" />
      </Stack.Protected>
      <Stack.Protected guard={offerBiometric}>
        <Stack.Screen name="onboarding/biometric" />
      </Stack.Protected>
      <Stack.Protected guard={ready}>
        <Stack.Screen name="(main)" />
      </Stack.Protected>
    </Stack>
  );
}
