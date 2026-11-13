import { Stack } from "expo-router";
import { useEffect } from "react";

import { LoadingView, RetryView } from "@/components/state-view";
import { needsConsent, useConsents } from "@/features/consents/use-consents";
import { useBiometricState } from "@/features/lock/biometric";
import { useWizardActive } from "@/features/records/onboarding-store";
import { ownProfile, usePatients } from "@/features/records/use-profile";
import { startCachePersistence } from "@/lib/persist";
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
  const consented = Boolean(consents.data) && !needsConsent(consents.data ?? []);
  // health data (the profiles) only once the consents are given (server: 403 before)
  const patients = usePatients({ enabled: consented });
  const wizardActive = useWizardActive();
  // The saved records (encrypted, `meta.persist`) as soon as the consents are known to be
  // given, not only once Home is up: Home then opens on them while the network refreshes
  // them (Phase 6 DoD - Home p95 < 1.5 s). useLocalData in (main) awaits the same start.
  useEffect(() => {
    if (consented) void startCachePersistence().catch(() => undefined);
  }, [consented]);

  if (consents.isPending || biometric.isPending) return <LoadingView />;
  // Fail closed without known consent state; a failed background refresh keeps the last one.
  if (!consents.data) {
    return <RetryView text={errorText(consents.error)} onRetry={() => void consents.refetch()} />;
  }
  const mustConsent = needsConsent(consents.data);
  const offerBiometric =
    !mustConsent && biometric.data?.available === true && biometric.data.choice === null;
  if (!mustConsent && !offerBiometric && !patients.data) {
    if (patients.isPending) return <LoadingView />;
    return <RetryView text={errorText(patients.error)} onRetry={() => void patients.refetch()} />;
  }
  // First sign-in: the transplant wizard until the own profile exists (it is created on the
  // first save or on skipping), and until the wizard itself is finished.
  const offerTransplant =
    !mustConsent && !offerBiometric && (wizardActive || !ownProfile(patients.data));
  const ready = !mustConsent && !offerBiometric && !offerTransplant;

  return (
    <Stack screenOptions={{ headerShown: false }}>
      <Stack.Protected guard={mustConsent}>
        <Stack.Screen name="onboarding/consents" />
      </Stack.Protected>
      <Stack.Protected guard={offerBiometric}>
        <Stack.Screen name="onboarding/biometric" />
      </Stack.Protected>
      <Stack.Protected guard={offerTransplant}>
        <Stack.Screen name="onboarding/transplant" />
      </Stack.Protected>
      <Stack.Protected guard={ready}>
        <Stack.Screen name="(main)" />
      </Stack.Protected>
    </Stack>
  );
}
