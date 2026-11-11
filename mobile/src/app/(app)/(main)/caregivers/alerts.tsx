import { useRouter } from "expo-router";
import { useEffect, useState } from "react";
import { Alert } from "react-native";
import { useTranslations } from "use-intl";

import { Button } from "@/components/button";
import { Choices } from "@/components/choices";
import { FormMessage } from "@/components/form-message";
import { Screen } from "@/components/screen";
import { LoadingView, RetryView } from "@/components/state-view";
import { Paragraph } from "@/components/text";
import { useAlerts, useLeave, useSetAlerts } from "@/features/caregivers/use-caregivers";
import { useRecordProfile } from "@/features/health/record-screens";
import { usePinnedProfile } from "@/features/records/active-profile";
import { ProfileBanner } from "@/features/records/profile-banner";
import { useErrorText } from "@/lib/use-error-text";

// the caregiver's own choice (15-240 minutes, or off - 2.8a); 30 is offered first (10e)
const DELAYS = [15, 20, 30, 45, 60, 90, 120, 180, 240] as const;
type Choice = number | "off";
const DEFAULT: Choice = 30;

/**
 * A caregiver's alerts for the profile shown (2.8e): after how long an unlogged dose is
 * announced, which medicines that covers, and what an alert - or no alert - does not mean.
 */
export default function CaregiverAlertsScreen() {
  const t = useTranslations("app.caregivers.alertSettings");
  const tc = useTranslations("app.common");
  const router = useRouter();
  const errorText = useErrorText();
  const { patients, own: active } = useRecordProfile();
  const { pinned: own, changed } = usePinnedProfile(active);
  const alerts = useAlerts(own?.access_level === "caregiver" ? own.id : undefined);
  const save = useSetAlerts(own?.id ?? "");
  const leave = useLeave(own?.id ?? "");
  const [choice, setChoice] = useState<Choice | null>(null);
  const [saved, setSaved] = useState(false);

  // the stored choice, or 30 minutes offered before anything was chosen
  useEffect(() => {
    if (!alerts.data || choice !== null) return;
    const stored = alerts.data.missed_dose_after_min;
    setChoice(!alerts.data.chosen ? DEFAULT : stored === null ? "off" : (stored as Choice));
  }, [alerts.data, choice]);

  if (changed) {
    return (
      <Screen>
        <Paragraph>{t("changed")}</Paragraph>
      </Screen>
    );
  }
  if (patients.isPending) return <LoadingView />;
  if (own?.access_level !== "caregiver") {
    return (
      <Screen>
        <Paragraph>{t("notCaregiver")}</Paragraph>
      </Screen>
    );
  }
  if (alerts.isPending || choice === null) return <LoadingView />;
  if (!alerts.data) {
    return <RetryView text={errorText(alerts.error)} onRetry={() => void alerts.refetch()} />;
  }
  const leaveNow = () =>
    Alert.alert(
      t("leaveTitle", { name: own.full_name }),
      t("leaveBody"),
      [
        { text: tc("cancel"), style: "cancel" },
        {
          text: t("leaveConfirm"),
          style: "destructive",
          onPress: () =>
            leave.mutate(undefined, {
              onSuccess: () => router.back(),
            }),
        },
      ],
      { cancelable: true },
    );
  return (
    <Screen>
      <ProfileBanner />
      {alerts.data.owner_paused && <FormMessage kind="warning" text={t("paused")} />}
      <Choices
        label={t("delay")}
        options={
          typeof choice === "number" && !(DELAYS as readonly number[]).includes(choice)
            ? ([...DELAYS, choice, "off"] as Choice[])
            : ([...DELAYS, "off"] as Choice[])
        }
        value={choice}
        labelOf={(c) => (c === "off" ? t("off") : t("minutes", { minutes: c }))}
        onSelect={(c) => {
          setChoice(c);
          setSaved(false);
        }}
        columns={2}
      />
      {(choice === 15 || choice === 20) && <FormMessage kind="warning" text={t("shortNote")} />}
      <Paragraph>{t("watched", { count: alerts.data.watched_medications })}</Paragraph>
      {alerts.data.watched_medications === 0 && (
        <FormMessage kind="warning" text={t("watchedNone")} />
      )}
      <Paragraph muted>{t("onlyReminders")}</Paragraph>
      <Paragraph muted>{t("noAlertNote")}</Paragraph>
      <Button
        label={t("save")}
        busy={save.isPending}
        disabled={save.isPending}
        onPress={() =>
          save.mutate(
            {
              missed_dose_after_min: choice === "off" ? null : choice,
              critical_result: alerts.data.critical_result,
            },
            { onSuccess: () => setSaved(true) },
          )
        }
      />
      {saved && <FormMessage kind="success" text={t("saved")} />}
      {save.isError && <FormMessage kind="error" text={errorText(save.error)} />}
      <Button
        variant="danger"
        label={t("leave")}
        accessibilityLabel={t("leaveTitle", { name: own.full_name })}
        onPress={leaveNow}
        disabled={leave.isPending}
      />
      {leave.isError && <FormMessage kind="error" text={errorText(leave.error)} />}
    </Screen>
  );
}
