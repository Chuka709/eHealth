import { Host, Switch } from "@expo/ui";
import { radius, space } from "@labtrack/shared";
import { useRouter } from "expo-router";
import { Alert, StyleSheet, View } from "react-native";
import { useTranslations } from "use-intl";

import { Button } from "@/components/button";
import { FormMessage } from "@/components/form-message";
import { NavGroup, NavRow } from "@/components/nav-row";
import { Screen } from "@/components/screen";
import { Paragraph } from "@/components/text";
import { signOut } from "@/features/auth/session";
import { LOCK_AFTER_MINUTES } from "@/features/lock/biometric";
import { useBiometricToggle } from "@/features/lock/use-biometric-toggle";
import { usePalette } from "@/theme/use-palette";

export default function SettingsScreen() {
  const t = useTranslations("app");
  const router = useRouter();
  const p = usePalette();
  const biometric = useBiometricToggle(t("lock.prompt"), t("settings.biometricDisablePrompt"));

  const confirmSignOut = () =>
    Alert.alert(
      t("settings.signOutConfirmTitle"),
      t("settings.signOutConfirmBody"),
      [
        { text: t("common.cancel"), style: "cancel" },
        { text: t("settings.signOut"), style: "destructive", onPress: () => void signOut() },
      ],
      { cancelable: true },
    );

  return (
    <Screen>
      <NavGroup title={t("settings.groups.health")}>
        <NavRow
          icon="card-account-details-outline"
          label={t("emergency.title")}
          hint={t("emergency.unlocked.openHint")}
          onPress={() => router.push("/settings/emergency")}
          testID="settings-emergency"
        />
        <NavRow
          icon="alarm"
          label={t("meds.reminders.open")}
          hint={t("meds.reminders.openHint")}
          onPress={() => router.push("/settings/reminders")}
          testID="settings-reminders"
        />
      </NavGroup>
      <NavGroup title={t("settings.groups.caregivers")}>
        <NavRow
          icon="account-heart-outline"
          label={t("caregivers.invitations.open")}
          hint={t("caregivers.invitations.openHint")}
          onPress={() => router.push("/caregivers/invitations" as never)}
          testID="settings-invitations"
        />
      </NavGroup>
      <NavGroup title={t("settings.groups.account")}>
        <NavRow
          icon="account-circle-outline"
          label={t("settings.profile")}
          hint={t("settings.profileHint")}
          onPress={() => router.push("/settings/profile")}
          testID="settings-profile"
        />
        <NavRow
          icon="lock-reset"
          label={t("settings.password")}
          onPress={() => router.push("/settings/password")}
          testID="settings-password"
        />
        <NavRow
          icon="cellphone-link"
          label={t("settings.devices")}
          hint={t("settings.devicesHint")}
          onPress={() => router.push("/settings/devices")}
          testID="settings-devices"
        />
      </NavGroup>
      <NavGroup title={t("settings.groups.privacy")}>
        <NavRow
          icon="shield-check-outline"
          label={t("consentSettings.open")}
          hint={t("consentSettings.hint")}
          onPress={() => router.push("/settings/consents")}
          testID="settings-consents"
        />
        <NavRow
          icon="history"
          label={t("adminHistory.open")}
          hint={t("adminHistory.hint")}
          onPress={() => router.push("/settings/admin-history")}
          testID="settings-admin-history"
        />
      </NavGroup>
      <NavGroup title={t("settings.groups.app")}>
        <NavRow
          icon="information-outline"
          label={t("about.open")}
          hint={t("about.hint")}
          onPress={() => router.push("/settings/about")}
          testID="settings-about"
        />
      </NavGroup>
      {/* Its own block: the switch's label is the only label (nothing read twice). */}
      <View style={[styles.block, { backgroundColor: p.surface, borderColor: p.border }]}>
        <Host matchContents={{ vertical: true }} style={styles.wide}>
          <Switch
            label={t("settings.biometric")}
            value={biometric.on}
            disabled={biometric.busy || (!biometric.available && !biometric.on)}
            onValueChange={(on) => void biometric.setOn(on)}
            testID="settings-biometric"
          />
        </Host>
        <Paragraph muted>
          {biometric.available
            ? t("settings.biometricHint", { minutes: LOCK_AFTER_MINUTES })
            : t("settings.biometricUnavailable")}
        </Paragraph>
        {biometric.failed && <FormMessage kind="error" text={t("settings.biometricFailed")} />}
      </View>
      <View style={styles.separated}>
        <Button variant="danger" label={t("settings.signOut")} onPress={confirmSignOut} />
      </View>
      <View style={styles.separated}>
        <NavRow
          tone="danger"
          icon="delete-outline"
          label={t("deleteAccount.open")}
          hint={t("deleteAccount.hint")}
          onPress={() => router.push("/settings/delete-account")}
          testID="settings-delete-account"
        />
      </View>
    </Screen>
  );
}

const styles = StyleSheet.create({
  block: {
    gap: space.sm,
    padding: space.md,
    borderRadius: radius.md,
    borderWidth: StyleSheet.hairlineWidth * 2,
  },
  wide: { width: "100%" },
  separated: { marginTop: space.xl },
});
