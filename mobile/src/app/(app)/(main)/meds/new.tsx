import { useRouter } from "expo-router";
import { LoadingView, RetryView } from "@/components/state-view";
import { MedicationForm } from "@/features/meds/med-form";
import { useActiveProfile, usePinnedProfile } from "@/features/records/active-profile";
import { ProfileChanged } from "@/features/records/profile-changed";
import { usePatients } from "@/features/records/use-profile";
import { useErrorText } from "@/lib/use-error-text";

export default function NewMedicationScreen() {
  const router = useRouter();
  const errorText = useErrorText();
  const patients = usePatients();
  const active = useActiveProfile(patients.data);
  const { pinned: own, changed } = usePinnedProfile(active);
  if (changed) return <ProfileChanged />;
  if (patients.isPending) return <LoadingView />;
  if (!own) {
    return <RetryView text={errorText(patients.error)} onRetry={() => void patients.refetch()} />;
  }
  return <MedicationForm patientId={own.id} onDone={() => router.back()} />;
}
