import { Host, Switch } from "@expo/ui";
import { useEffect, useState } from "react";
import { StyleSheet } from "react-native";
import { useTranslations } from "use-intl";
import { FormMessage } from "@/components/form-message";
import { Paragraph } from "@/components/text";

import { medAlarmChoices, medAlarmOn, setMedAlarm } from "./notify";
import { requestReminderSync } from "./reminder-bus";

/**
 * Whether this medicine's reminders ring like an alarm through silent mode (Q79-3, Android
 * only - the caller shows it there): this phone's choice, by default on for immunosuppressants,
 * corticosteroids and a medicine of no known kind. Only for the user's own reminded medicines -
 * other profiles are not reminded on this phone.
 */
export function MedAlarmSwitch({
  medication,
}: {
  medication: { id: string; category: string | null };
}) {
  const t = useTranslations("app.meds.detail");
  const [on, setOn] = useState<boolean | null>(null);
  const [saving, setSaving] = useState(false);
  const [failed, setFailed] = useState(false);
  const { id, category } = medication;

  useEffect(() => {
    let live = true;
    void medAlarmChoices()
      .then((choices) => live && setOn(medAlarmOn({ id, category }, choices)))
      .catch(() => live && setOn(medAlarmOn({ id, category }, {})));
    return () => {
      live = false;
    };
  }, [id, category]);

  return (
    <>
      <Host matchContents={{ vertical: true }} style={styles.wide}>
        <Switch
          label={t("alarmMed")}
          value={on ?? false}
          disabled={on === null || saving}
          onValueChange={(value) => {
            setOn(value);
            setSaving(true);
            setFailed(false);
            void setMedAlarm(id, value)
              .then(
                () => requestReminderSync(),
                () => {
                  setOn(!value); // not kept: the switch shows what is in force
                  setFailed(true);
                },
              )
              .finally(() => setSaving(false));
          }}
          testID="med-alarm"
        />
      </Host>
      {failed && <FormMessage kind="error" text={t("alarmMedFailed")} />}
      <Paragraph muted>{t("alarmMedHint")}</Paragraph>
    </>
  );
}

const styles = StyleSheet.create({ wide: { alignSelf: "stretch" } });
