import { useRouter } from "expo-router";
import { AccessibilityInfo } from "react-native";
import { useTranslations } from "use-intl";

import { Choices } from "@/components/choices";
import { Screen } from "@/components/screen";
import { LoadingView, RetryView } from "@/components/state-view";
import { Paragraph } from "@/components/text";
import { setActiveProfile, useActiveProfile } from "@/features/records/active-profile";
import { type Patient, usePatients } from "@/features/records/use-profile";
import { useErrorText } from "@/lib/use-error-text";

/** Choosing whose records the record screens show (own profile, a child's, someone cared for). */
export default function ProfilesScreen() {
  const t = useTranslations("app.profiles");
  const router = useRouter();
  const errorText = useErrorText();
  const patients = usePatients();
  const active = useActiveProfile(patients.data);

  if (patients.isPending) return <LoadingView />;
  if (!patients.data) {
    return <RetryView text={errorText(patients.error)} onRetry={() => void patients.refetch()} />;
  }
  const byId = new Map(patients.data.map((p) => [p.id, p]));
  const labelOf = (id: string) => {
    const p = byId.get(id) as Patient;
    const relation = p.relation === "child" ? ` · ${t("relation.child")}` : "";
    return `${p.full_name}${relation} · ${t(`level.${p.access_level}`)}`;
  };
  return (
    <Screen>
      <Paragraph>{t("intro")}</Paragraph>
      <Choices
        label={t("title")}
        options={patients.data.map((p) => p.id)}
        value={active?.id ?? null}
        labelOf={labelOf}
        onSelect={(id) => {
          const own = byId.get(id)?.relation === "self" && byId.get(id)?.access_level === "owner";
          setActiveProfile(own ? null : id);
          AccessibilityInfo.announceForAccessibility(
            t("switched", { name: byId.get(id)?.full_name ?? "" }),
          );
          router.back();
        }}
        columns={1}
      />
      <Paragraph muted>{t("ownOnly")}</Paragraph>
    </Screen>
  );
}
