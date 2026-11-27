import { Host, Switch } from "@expo/ui";
import { useEffect, useState } from "react";
import { Linking, Platform, StyleSheet } from "react-native";
import { useTranslations } from "use-intl";
import { Button } from "@/components/button";
import { Screen } from "@/components/screen";
import { Paragraph, Title } from "@/components/text";
import {
  alarmSound,
  setAlarmSound,
  setShowAppointmentDetails,
  setShowNames,
  showAppointmentDetails,
  showNames,
} from "@/features/meds/notify";
import { useZones } from "@/features/meds/use-medications";
import {
  enableExactAlarms,
  hasAutostartSetting,
  openAutostart,
  openLockScreenPermission,
  useReminderHealth,
} from "@/features/meds/use-reminder-health";
import { requestReminderSync } from "@/features/meds/use-reminders";
import { zoneLabel } from "@/features/meds/use-zone-prompt";
import { ownProfile, usePatients } from "@/features/records/use-profile";

/** Reminder privacy (H10) and the zone "local" medicines follow (Q22). */
export default function RemindersSettingsScreen() {
  const t = useTranslations("app.meds.reminders");
  const th = useTranslations("app.meds.health");
  const health = useReminderHealth();
  const [asking, setAsking] = useState(false);
  const [names, setNames] = useState<boolean | null>(null);
  const [details, setDetails] = useState<boolean | null>(null);
  const [loud, setLoud] = useState<boolean | null>(null);
  const patients = usePatients();
  const zones = useZones(ownProfile(patients.data)?.id);

  useEffect(() => {
    void showNames()
      .then(setNames)
      .catch(() => setNames(false));
    void showAppointmentDetails()
      .then(setDetails)
      .catch(() => setDetails(false));
    void alarmSound()
      .then(setLoud)
      .catch(() => setLoud(true));
  }, []);

  return (
    <Screen>
      <Host matchContents={{ vertical: true }} style={styles.wide}>
        <Switch
          label={t("alarmSound")}
          value={loud ?? true}
          disabled={loud === null}
          onValueChange={(on) => {
            setLoud(on);
            void setAlarmSound(on).then(requestReminderSync);
          }}
          testID="reminders-alarm-sound"
        />
      </Host>
      <Paragraph muted>{t("alarmSoundHint")}</Paragraph>
      <Paragraph muted>{t("repeatHint")}</Paragraph>
      <Host matchContents={{ vertical: true }} style={styles.wide}>
        <Switch
          label={t("showNames")}
          value={names ?? false}
          disabled={names === null}
          onValueChange={(on) => {
            setNames(on);
            void setShowNames(on).then(requestReminderSync);
          }}
          testID="reminders-show-names"
        />
      </Host>
      <Paragraph muted>{t("showNamesHint")}</Paragraph>
      <Host matchContents={{ vertical: true }} style={styles.wide}>
        <Switch
          label={t("showDetails")}
          value={details ?? false}
          disabled={details === null}
          onValueChange={(on) => {
            setDetails(on);
            void setShowAppointmentDetails(on).then(requestReminderSync);
          }}
          testID="reminders-show-details"
        />
      </Host>
      <Paragraph muted>{t("showDetailsHint")}</Paragraph>
      {zones.data && <Paragraph>{t("zoneNow", { zone: zoneLabel(zones.data.current) })}</Paragraph>}
      <Paragraph muted>{t("zoneHome")}</Paragraph>

      {Platform.OS === "android" && (
        <>
          <Title>{th("exactTitle")}</Title>
          <Paragraph>{th("exactBody")}</Paragraph>
          {health.data?.exactOff === false && <Paragraph>{th("exactOk")}</Paragraph>}
          {health.data?.exactOff === true && (
            <Button
              label={th("exactAllow")}
              busy={asking}
              onPress={() => {
                setAsking(true);
                void enableExactAlarms()
                  .catch(() => undefined)
                  .finally(() => setAsking(false));
              }}
            />
          )}
          <Title>{th("batteryTitle")}</Title>
          <Paragraph>{th("batteryBody")}</Paragraph>
          <Paragraph>{th("batterySamsung")}</Paragraph>
          <Paragraph>{th("batteryXiaomi")}</Paragraph>
          {hasAutostartSetting() && (
            <Button
              label={th("autostartOpen")}
              variant="secondary"
              onPress={() => void openAutostart().catch(() => undefined)}
            />
          )}
          {hasAutostartSetting() && <Paragraph>{th("lockXiaomi")}</Paragraph>}
          {hasAutostartSetting() && (
            <Button
              label={th("lockOpen")}
              variant="secondary"
              onPress={() => void openLockScreenPermission().catch(() => undefined)}
            />
          )}
          <Paragraph>{th("batteryOppo")}</Paragraph>
          <Paragraph>{th("batteryOther")}</Paragraph>
          <Button
            label={th("openSettings")}
            variant="secondary"
            onPress={() => void Linking.openSettings()}
          />
        </>
      )}
    </Screen>
  );
}

const styles = StyleSheet.create({ wide: { alignSelf: "stretch" } });
