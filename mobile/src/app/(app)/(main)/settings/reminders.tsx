import { Host, Switch } from "@expo/ui";
import { useEffect, useState } from "react";
import { StyleSheet } from "react-native";
import { useTranslations } from "use-intl";

import { Screen } from "@/components/screen";
import { Paragraph } from "@/components/text";
import { setShowNames, showNames } from "@/features/meds/notify";
import { useZones } from "@/features/meds/use-medications";
import { requestReminderSync } from "@/features/meds/use-reminders";
import { zoneLabel } from "@/features/meds/use-zone-prompt";
import { ownProfile, usePatients } from "@/features/records/use-profile";

/** Reminder privacy (H10) and the zone "local" medicines follow (Q22). */
export default function RemindersSettingsScreen() {
  const t = useTranslations("app.meds.reminders");
  const [names, setNames] = useState<boolean | null>(null);
  const patients = usePatients();
  const zones = useZones(ownProfile(patients.data)?.id);

  useEffect(() => {
    void showNames()
      .then(setNames)
      .catch(() => setNames(false));
  }, []);

  return (
    <Screen>
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
      {zones.data && <Paragraph>{t("zoneNow", { zone: zoneLabel(zones.data.current) })}</Paragraph>}
      <Paragraph muted>{t("zoneHome")}</Paragraph>
    </Screen>
  );
}

const styles = StyleSheet.create({ wide: { alignSelf: "stretch" } });
