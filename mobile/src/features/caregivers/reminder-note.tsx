import { useTranslations } from "use-intl";

import { FormMessage } from "@/components/form-message";
import { usePatients } from "@/features/records/use-profile";

import { alertingCaregivers, useCaregivers } from "./use-caregivers";

/**
 * Shown to the profile's owner where a medicine's reminders are off while caregivers get dose
 * alerts: those alerts watch medicines with reminders only (2.8e), so this one is not watched.
 */
export function CaregiverReminderNote({
  patientId,
  remindersOn,
}: {
  patientId: string;
  remindersOn: boolean;
}) {
  const t = useTranslations("app.caregivers");
  const patients = usePatients();
  const owner = patients.data?.find((p) => p.id === patientId)?.access_level === "owner";
  const list = useCaregivers(patientId, { enabled: owner && !remindersOn });
  if (remindersOn || !owner || alertingCaregivers(list.data) === 0) return null;
  return <FormMessage kind="warning" text={t("reminderOffNote")} />;
}
