import { Alert } from "react-native";
import { useTranslations } from "use-intl";

import { Button } from "@/components/button";
import { FormMessage } from "@/components/form-message";
import { RetryView } from "@/components/state-view";
import { Paragraph } from "@/components/text";
import { allergyRow } from "@/features/health/forms";
import { RecordList, useRecordProfile } from "@/features/health/record-screens";
import {
  ALLERGIES,
  useNoKnownAllergies,
  useRecords,
  useSetNoKnownAllergies,
} from "@/features/health/use-health";
import { formatDate } from "@/lib/dates";
import { useErrorText } from "@/lib/use-error-text";

export default function AllergiesScreen() {
  const t = useTranslations("app.health");
  return (
    <RecordList
      kind={ALLERGIES as never}
      route="/allergies"
      row={allergyRow(t as (k: string) => string) as never}
      addLabel={t("allergy.new")}
      header={<NoKnownAllergies />}
    />
  );
}

/**
 * "No known allergies", confirmed and dated (Q39 ★): unlike an empty list, which only means
 * none recorded (H17). Offered only while no allergy is recorded; adding one ends it (0048).
 */
function NoKnownAllergies() {
  const t = useTranslations("app.health.nka");
  const errorText = useErrorText();
  const { own } = useRecordProfile();
  const list = useRecords(ALLERGIES, own?.id);
  const nka = useNoKnownAllergies(own?.id);
  const set = useSetNoKnownAllergies(own?.id ?? "");
  if (!own || !list.data || list.data.length > 0 || nka.isPending) return null;
  if (nka.isError) {
    return <RetryView text={errorText(nka.error)} onRetry={() => void nka.refetch()} />;
  }
  const writer = own.access_level === "owner" || own.access_level === "caregiver";
  const ask = (confirm: boolean) =>
    Alert.alert(
      confirm ? t("confirmTitle") : t("clearTitle"),
      confirm ? t("confirmBody") : t("clearBody"),
      [
        { text: t("cancel"), style: "cancel" },
        {
          text: confirm ? t("confirm") : t("clear"),
          style: confirm ? "default" : "destructive",
          onPress: () => set.mutate(confirm),
        },
      ],
    );
  return (
    <>
      {nka.data ? (
        <FormMessage
          kind="success"
          text={t("confirmed", { date: formatDate(`${nka.data}T12:00:00Z`) })}
        />
      ) : (
        <Paragraph muted>{t(writer ? "hint" : "hintReadOnly")}</Paragraph>
      )}
      {writer && (
        <Button
          label={nka.data ? t("clear") : t("confirm")}
          variant="secondary"
          disabled={set.isPending}
          onPress={() => ask(!nka.data)}
        />
      )}
      {set.isError && <FormMessage kind="error" text={errorText(set.error)} />}
    </>
  );
}
