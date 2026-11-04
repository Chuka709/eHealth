import { useRouter } from "expo-router";

import { LoadingView, RetryView } from "@/components/state-view";
import { MedicationForm } from "@/features/meds/med-form";
import { ownProfile, usePatients } from "@/features/records/use-profile";
import { useErrorText } from "@/lib/use-error-text";

export default function NewMedicationScreen() {
  const router = useRouter();
  const errorText = useErrorText();
  const patients = usePatients();
  const own = ownProfile(patients.data);
  if (patients.isPending) return <LoadingView />;
  if (!own) {
    return <RetryView text={errorText(patients.error)} onRetry={() => void patients.refetch()} />;
  }
  return <MedicationForm patientId={own.id} onDone={() => router.back()} />;
}
