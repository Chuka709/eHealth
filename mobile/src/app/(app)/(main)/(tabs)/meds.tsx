import { useRouter } from "expo-router";
import { useTranslations } from "use-intl";
import { Button } from "@/components/button";
import { NavRow } from "@/components/nav-row";
import { Screen } from "@/components/screen";
import { LoadingView, RetryView } from "@/components/state-view";
import { Paragraph, Title } from "@/components/text";
import { MonthSummary } from "@/features/meds/month-summary";
import { TodayList } from "@/features/meds/today-list";
import { useRegimenText } from "@/features/meds/use-med-text";
import { useNow } from "@/features/meds/use-now";
import { useTodayDoses } from "@/features/meds/use-today";
import { ownProfile, usePatients } from "@/features/records/use-profile";
import { useErrorText } from "@/lib/use-error-text";

export default function MedsScreen() {
  const t = useTranslations("app.meds");
  const router = useRouter();
  const errorText = useErrorText();
  const regimenText = useRegimenText();
  const now = useNow();
  const patients = usePatients();
  const own = ownProfile(patients.data);
  const { doses, meds } = useTodayDoses(own?.id, now);

  if (patients.isPending || (own && meds.isPending)) return <LoadingView />;
  if (!own || !meds.data) {
    return (
      <RetryView
        text={errorText(patients.error ?? meds.error)}
        onRetry={() => void (patients.data ? meds.refetch() : patients.refetch())}
      />
    );
  }
  const current = meds.data.filter((m) => m.is_current);
  const past = meds.data.filter((m) => !m.is_current);

  return (
    <Screen>
      <Title>{t("today")}</Title>
      <TodayList patientId={own.id} doses={doses} now={now.getTime()} />
      <MonthSummary patientId={own.id} now={now} />

      <Title>{t("current")}</Title>
      {current.length === 0 && <Paragraph>{t("noMeds")}</Paragraph>}
      {current.map((m) => (
        <NavRow
          key={m.id}
          label={m.strength ? `${m.name} ${m.strength}` : m.name}
          hint={regimenText(m.current_regimen)}
          onPress={() => router.push({ pathname: "/meds/[id]", params: { id: m.id } })}
          testID={`med-${m.id}`}
        />
      ))}
      <Button label={t("add")} onPress={() => router.push("/meds/new")} />

      {past.length > 0 && <Title>{t("past")}</Title>}
      {past.map((m) => (
        <NavRow
          key={m.id}
          label={m.strength ? `${m.name} ${m.strength}` : m.name}
          hint={regimenText(m.regimens.find((r) => r.voided_at === null))}
          onPress={() => router.push({ pathname: "/meds/[id]", params: { id: m.id } })}
        />
      ))}
    </Screen>
  );
}
