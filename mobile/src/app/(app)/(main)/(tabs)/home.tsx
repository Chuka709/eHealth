import { useRouter } from "expo-router";
import { useTranslations } from "use-intl";
import { NavRow } from "@/components/nav-row";
import { Screen } from "@/components/screen";
import { EmergencyCardOffer } from "@/features/emergency/card-offer";
import { LabSections } from "@/features/home/dashboard-sections";
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
 * Home (Phase 2.9, 6.8): today's doses with one-tap "Уусан", lab values worth a look and the
 * key cards (6.8), the latest transplant, the next
 * appointment - for the profile the record screens show. The account's own notices and
 * reminder warnings come first. Loading /me applies the language.
 */
export default function HomeScreen() {
  const t = useTranslations();
  const router = useRouter();
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
        <ProfileSections
          key={active.id}
          patientId={active.id}
          now={now}
          canEdit={active.access_level === "owner" || active.access_level === "caregiver"}
        />
      )}
      {active && (
        <NavRow
          icon="file-document-multiple-outline"
          label={t("app.upload.rowLabel")}
          hint={t("app.upload.rowHint")}
          onPress={() => router.push("/results")}
          testID="home-results"
        />
      )}
      <EmergencyCardOffer />
      {/* the server connection only when it is a problem (2.12): no developer status on Home */}
      <HealthStatus problemsOnly />
    </Screen>
  );
}

function ProfileSections({
  patientId,
  now,
  canEdit,
}: {
  patientId: string;
  now: Date;
  canEdit: boolean;
}) {
  return (
    <>
      {/* the daily action first, within thumb reach */}
      <TodaySection patientId={patientId} now={now} />
      {/* confirmed lab values worth a look, then the key cards (Phase 6.8) */}
      <LabSections patientId={patientId} canEdit={canEdit} />
      <TransplantSection patientId={patientId} />
      <AppointmentSection patientId={patientId} now={now} />
    </>
  );
}
