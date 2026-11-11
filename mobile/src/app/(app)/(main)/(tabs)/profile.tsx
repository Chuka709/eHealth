import { useRouter } from "expo-router";
import { useTranslations } from "use-intl";
import { NavGroup, NavRow } from "@/components/nav-row";
import { Screen } from "@/components/screen";
import { useRecordProfile } from "@/features/health/record-screens";
import {
  ALLERGIES,
  type Allergy,
  APPOINTMENTS,
  type Appointment,
  CONTACTS,
  type Contact,
  QUESTIONS,
  type Question,
  useRecords,
} from "@/features/health/use-health";
import { ProfileSwitcher } from "@/features/records/profile-switcher";
import { formatDateTime } from "@/lib/dates";

/** The health profile: one place for everything the user keeps about their care. */
export default function ProfileScreen() {
  const t = useTranslations("app.health");
  const tg = useTranslations("app.caregivers");
  const tu = useTranslations("app.upload");
  const router = useRouter();
  const { own } = useRecordProfile();
  const appointments = useRecords(APPOINTMENTS, own?.id);
  const allergies = useRecords(ALLERGIES, own?.id);
  const contacts = useRecords(CONTACTS, own?.id);
  const questions = useRecords(QUESTIONS, own?.id);
  const now = Date.now();
  const next = ((appointments.data ?? []) as Appointment[])
    .filter((a) => a.status === "planned" && Date.parse(a.scheduled_at) >= now)
    .sort((a, b) => Date.parse(a.scheduled_at) - Date.parse(b.scheduled_at))[0];
  const allergyList = (allergies.data ?? []) as Allergy[];
  const open = ((questions.data ?? []) as Question[]).filter((q) => q.status === "open").length;
  const go = (path: string) => () => router.push(path as never);
  // never an empty claim ("no allergy recorded") when a list could not be read
  const known = (q: { data?: unknown; isError: boolean }, text: () => string) =>
    q.data ? text() : q.isError ? t("loadFailed") : undefined;
  return (
    <Screen>
      <ProfileSwitcher />
      <NavGroup title={t("groups.care")}>
        <NavRow
          icon="heart-plus-outline"
          label={t("transplants")}
          onPress={go("/transplants")}
          testID="profile-transplants"
        />
        <NavRow
          icon="clipboard-text-clock-outline"
          label={t("events")}
          onPress={go("/events")}
          testID="profile-events"
        />
        <NavRow
          icon="calendar-clock"
          label={t("appointments")}
          hint={known(appointments, () =>
            next
              ? t("nextAppointment", {
                  when: `${formatDateTime(next.scheduled_at)} · ${next.title}`,
                })
              : t("noAppointment"),
          )}
          onPress={go("/appointments")}
          testID="profile-appointments"
        />
      </NavGroup>
      <NavGroup title={t("groups.health")}>
        <NavRow
          icon="file-document-multiple-outline"
          label={tu("rowLabel")}
          hint={tu("rowHint")}
          onPress={go("/results")}
          testID="profile-results"
        />
        <NavRow
          icon="heart-pulse"
          label={t("vitals")}
          onPress={go("/vitals")}
          testID="profile-vitals"
        />
        <NavRow
          icon="alert-circle-outline"
          label={t("allergies")}
          hint={known(allergies, () =>
            allergyList.length
              ? allergyList
                  .slice(0, 3)
                  .map((a) => a.substance)
                  .join(", ") + (allergyList.length > 3 ? ` +${allergyList.length - 3}` : "")
              : t("noAllergy"),
          )}
          onPress={go("/allergies")}
          testID="profile-allergies"
        />
        <NavRow
          icon="comment-question-outline"
          label={t("questions")}
          hint={known(questions, () =>
            open === 0 ? t("openQuestionsNone") : t("openQuestions", { n: open }),
          )}
          onPress={go("/questions")}
          testID="profile-questions"
        />
      </NavGroup>
      <NavGroup title={t("groups.people")}>
        <NavRow
          icon="phone-outline"
          label={t("contacts")}
          hint={known(contacts, () =>
            t("contactCount", { n: ((contacts.data ?? []) as Contact[]).length }),
          )}
          onPress={go("/contacts")}
          testID="profile-contacts"
        />
        {own?.access_level === "owner" && !own.is_minor && (
          <NavRow
            icon="account-group-outline"
            label={tg("rowOwner")}
            hint={tg("rowOwnerHint")}
            onPress={go("/caregivers")}
            testID="profile-caregivers"
          />
        )}
        {own?.access_level === "caregiver" && (
          <NavRow
            icon="bell-ring-outline"
            label={tg("rowCaregiver")}
            hint={tg("rowCaregiverHint")}
            onPress={go("/caregivers/alerts")}
            testID="profile-caregiver-alerts"
          />
        )}
      </NavGroup>
    </Screen>
  );
}
