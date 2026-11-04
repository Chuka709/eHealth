import { useRouter } from "expo-router";
import { useTranslations } from "use-intl";

import { Button } from "@/components/button";
import { NavRow } from "@/components/nav-row";
import { Screen } from "@/components/screen";
import { LoadingView, RetryView } from "@/components/state-view";
import { Paragraph } from "@/components/text";
import { elapsedText, transplantDateText } from "@/features/records/elapsed";
import { ownProfile, usePatients } from "@/features/records/use-profile";
import { useTransplants } from "@/features/records/use-transplants";
import { useErrorText } from "@/lib/use-error-text";

export default function TransplantsScreen() {
  const t = useTranslations("app.transplant");
  const router = useRouter();
  const errorText = useErrorText();
  const patients = usePatients();
  const own = ownProfile(patients.data);
  const transplants = useTransplants(own?.id);

  if (patients.isPending || (own && transplants.isPending)) return <LoadingView />;
  const failed = patients.error ?? transplants.error;
  if (!patients.data || (own && !transplants.data)) {
    return (
      <RetryView
        text={errorText(failed)}
        onRetry={() => void (patients.data ? transplants.refetch() : patients.refetch())}
      />
    );
  }
  const list = transplants.data ?? [];

  return (
    <Screen>
      {list.length === 0 && <Paragraph>{t("empty")}</Paragraph>}
      {list.map((item) => {
        const since = elapsedText(t, item);
        const organ = t(`organ.${item.organ}`);
        return (
          <NavRow
            key={item.id}
            label={`${organ} · ${transplantDateText(item)}`}
            hint={[item.hospital, since].filter(Boolean).join(" · ")}
            onPress={() => router.push(`/transplants/${item.id}`)}
          />
        );
      })}
      <Button label={t("add")} onPress={() => router.push("/transplants/new")} />
    </Screen>
  );
}
