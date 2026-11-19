import { space } from "@labtrack/shared";
import { useRouter } from "expo-router";
import { StyleSheet, View } from "react-native";
import { useTranslations } from "use-intl";

import { Button } from "@/components/button";
import { FormMessage } from "@/components/form-message";
import { ownProfile, usePatients } from "@/features/records/use-profile";

import { useMedications } from "./use-medications";
import {
  confirmAutostart,
  enableNotifications,
  openAutostart,
  useReminderHealth,
} from "./use-reminder-health";

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
  const { notificationsOff, exactOff, canAsk, autostartHint } = health.data;
  // "may be late" only where asked (Medicines), quietly: reminders still come. Never two quiet
  // warnings at once: the autostart one (reminders stop after a restart) goes first
  const autostart = late && autostartHint && !notificationsOff;
  if (!notificationsOff && !(late && exactOff === true) && !autostart) return null;
  return (
    <View style={styles.group} testID="reminder-warnings">
      {autostart && (
        <>
          <FormMessage kind="warning" quiet text={t("autostartOff")} />
          <Button
            label={t("autostartOpen")}
            variant="secondary"
            onPress={() => void openAutostart().catch(() => undefined)}
          />
          <Button
            label={t("autostartDone")}
            variant="link"
            onPress={() => void confirmAutostart().catch(() => undefined)}
          />
        </>
      )}
      {notificationsOff ? (
        <>
          <FormMessage kind="error" text={t("notificationsOff")} />
          <Button
            label={canAsk ? t("notificationsOn") : t("openSettings")}
            onPress={() => void enableNotifications(canAsk).catch(() => undefined)}
          />
        </>
      ) : exactOff !== true || !late || autostart ? null : (
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
