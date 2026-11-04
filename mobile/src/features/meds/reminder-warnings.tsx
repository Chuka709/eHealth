import { space } from "@labtrack/shared";
import { useRouter } from "expo-router";
import { StyleSheet, View } from "react-native";
import { useTranslations } from "use-intl";

import { Button } from "@/components/button";
import { FormMessage } from "@/components/form-message";
import { ownProfile, usePatients } from "@/features/records/use-profile";

import { useMedications } from "./use-medications";
import { enableNotifications, useReminderHealth } from "./use-reminder-health";

/**
 * Home and Medicines: say plainly when reminders cannot work (H6 - notifications off) or may
 * be late (H18 - Android exact alarms not allowed), with the way to fix it. Only while some
 * medicine has reminders on; nothing when all is well.
 */
export function ReminderWarnings({ late = false }: { late?: boolean }) {
  const t = useTranslations("app.meds.health");
  const router = useRouter();
  const patients = usePatients();
  const meds = useMedications(ownProfile(patients.data)?.id);
  const health = useReminderHealth();
  const reminded = meds.data?.some((m) => m.is_current && m.reminders_enabled) ?? false;
  if (!reminded || !health.data) return null;
  const { notificationsOff, exactOff, canAsk } = health.data;
  // "may be late" only where asked (Medicines), quietly: reminders still come
  if (!notificationsOff && !(late && exactOff === true)) return null;
  return (
    <View style={styles.group} testID="reminder-warnings">
      {notificationsOff ? (
        <>
          <FormMessage kind="error" text={t("notificationsOff")} />
          <Button
            label={canAsk ? t("notificationsOn") : t("openSettings")}
            onPress={() => void enableNotifications(canAsk).catch(() => undefined)}
          />
        </>
      ) : (
        <>
          <FormMessage kind="warning" quiet text={t("exactOff")} />
          <Button
            label={t("exactMore")}
            variant="secondary"
            onPress={() => router.push("/settings/reminders")}
          />
        </>
      )}
    </View>
  );
}

const styles = StyleSheet.create({ group: { gap: space.sm } });
