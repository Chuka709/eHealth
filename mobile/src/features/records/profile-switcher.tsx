import { useRouter } from "expo-router";
import { useTranslations } from "use-intl";

import { NavRow } from "@/components/nav-row";

import { isOthers, useActiveProfile } from "./active-profile";
import { usePatients } from "./use-profile";

/**
 * At the top of the record screens, when the user has more than one profile: whose records
 * these are, and the way to switch. On someone else's profile it says so plainly - what is
 * recorded here is recorded for them (decision 4; H20 keeps who recorded it).
 */
export function ProfileSwitcher() {
  const t = useTranslations("app.profiles");
  const router = useRouter();
  const patients = usePatients();
  const active = useActiveProfile(patients.data);
  if (!active || (patients.data?.length ?? 0) < 2) return null;
  return (
    <NavRow
      label={
        isOthers(active, patients.data)
          ? `👤 ${t("current", { name: active.full_name })}`
          : t("current", { name: active.full_name })
      }
      hint={isOthers(active, patients.data) ? `${t("forOther")} ${t("switch")}` : t("switch")}
      onPress={() => router.push("/profiles" as never)}
      testID="profile-switcher"
    />
  );
}
