import { Host, Switch } from "@expo/ui";
import { useRouter } from "expo-router";
import { StyleSheet } from "react-native";
import { useTranslations } from "use-intl";

import { Button } from "@/components/button";
import { FormMessage } from "@/components/form-message";
import { Screen } from "@/components/screen";
import { LoadingView } from "@/components/state-view";
import { Paragraph } from "@/components/text";
import { useSetCardUnlocked, useUnlockedProfiles } from "@/features/emergency/use-unlocked-card";
import { useOwnProfile } from "@/features/health/record-screens";
import { useBiometricState } from "@/features/lock/biometric";

/**
 * Emergency card settings: whether the locked app may show the saved card (off by default,
 * user decision 10e). The risk is said before the switch (H17, H22). The choice stays on this
 * phone.
 */
export default function EmergencySettingsScreen() {
  const e = useTranslations("app.emergency.unlocked");
  const router = useRouter();
  const { patients, own } = useOwnProfile();
  const unlocked = useUnlockedProfiles();
  const setUnlocked = useSetCardUnlocked();
  const biometric = useBiometricState();
  if (patients.isPending || unlocked.isPending) return <LoadingView />;
  const on = Boolean(own && unlocked.data?.includes(own.id));
  return (
    <Screen>
      <Paragraph>{e("body")}</Paragraph>
      <Paragraph>{e("risk")}</Paragraph>
      {own ? (
        <Host matchContents={{ vertical: true }} style={styles.wide}>
          <Switch
            label={e("switch")}
            value={on}
            disabled={setUnlocked.isPending}
            onValueChange={(next) => setUnlocked.mutate({ patientId: own.id, on: next })}
            testID="emergency-unlocked"
          />
        </Host>
      ) : (
        <Paragraph>{e("noProfile")}</Paragraph>
      )}
      {setUnlocked.isError && <FormMessage kind="error" text={e("failed")} />}
      {biometric.data?.choice !== "on" && <Paragraph muted>{e("noLock")}</Paragraph>}
      <Paragraph muted>{e("phoneLock")}</Paragraph>
      <Button variant="secondary" label={e("view")} onPress={() => router.push("/emergency")} />
    </Screen>
  );
}

const styles = StyleSheet.create({ wide: { alignSelf: "stretch" } });
