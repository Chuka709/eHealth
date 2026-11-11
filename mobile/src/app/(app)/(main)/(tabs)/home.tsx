import { Screen } from "@/components/screen";
import { EmergencyCardOffer } from "@/features/emergency/card-offer";
import { AppointmentSection, TodaySection, TransplantSection } from "@/features/home/home-sections";
import { AdminNoticeBanner } from "@/features/me/admin-notice-banner";
import { useMe } from "@/features/me/use-me";
import { ReminderWarnings } from "@/features/meds/reminder-warnings";
import { useNow } from "@/features/meds/use-now";
import { useActiveProfile } from "@/features/records/active-profile";
import { ProfileSwitcher } from "@/features/records/profile-switcher";
import { usePatients } from "@/features/records/use-profile";
import { HealthStatus } from "@/features/status/health-status";

/**
 * Home (Phase 2.9): today's doses with one-tap "Уусан", the latest transplant, the next
 * appointment - for the profile the record screens show. The account's own notices and
 * reminder warnings come first. Loading /me applies the language.
 */
export default function HomeScreen() {
  useMe();
  const now = useNow();
  const patients = usePatients();
  const active = useActiveProfile(patients.data);
  return (
    <Screen testID="home-screen">
      <AdminNoticeBanner />
      <ReminderWarnings />
      <ProfileSwitcher />
      {active && (
        // keyed: a profile switch starts every section afresh (no row kept from the last one)
        <ProfileSections key={active.id} patientId={active.id} now={now} />
      )}
      <EmergencyCardOffer />
      {/* the server connection only when it is a problem (2.12): no developer status on Home */}
      <HealthStatus problemsOnly />
    </Screen>
  );
}

function ProfileSections({ patientId, now }: { patientId: string; now: Date }) {
  return (
    <>
      {/* the daily action first, within thumb reach */}
      <TodaySection patientId={patientId} now={now} />
      <TransplantSection patientId={patientId} />
      <AppointmentSection patientId={patientId} now={now} />
    </>
  );
}
