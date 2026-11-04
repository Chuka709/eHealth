import { useLocalSearchParams, usePreventRemove, useRouter } from "expo-router";
import { useState } from "react";
import { AccessibilityInfo, Alert } from "react-native";
import { useTranslations } from "use-intl";

import { Button } from "@/components/button";
import { FormMessage } from "@/components/form-message";
import { Screen } from "@/components/screen";
import { LoadingView, RetryView } from "@/components/state-view";
import { Paragraph } from "@/components/text";
import { elapsedText } from "@/features/records/elapsed";
import { type Draft, draftFrom, stepComplete, toFields } from "@/features/records/transplant-draft";
import {
  DateSection,
  DonorSection,
  ExtraSection,
  OrganSection,
  PlaceSection,
} from "@/features/records/transplant-sections";
import { ownProfile, usePatients } from "@/features/records/use-profile";
import {
  type Transplant,
  useDeleteTransplant,
  useTransplants,
  useUpdateTransplant,
} from "@/features/records/use-transplants";
import { useErrorText } from "@/lib/use-error-text";

export default function TransplantScreen() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const errorText = useErrorText();
  const patients = usePatients();
  const own = ownProfile(patients.data);
  const transplants = useTransplants(own?.id, { fresh: true });
  const transplant = transplants.data?.find((x) => x.id === id);

  if (patients.isPending || (own && transplants.isPending)) return <LoadingView />;
  // The whole record is saved back (PUT): never start the form from a cache that may be
  // days old (offline) - only from what the server sent just now.
  if (own && transplants.isFetching && !transplants.isFetchedAfterMount) return <LoadingView />;
  if (!own || !transplant || !transplants.isFetchedAfterMount || transplants.isError) {
    return (
      <RetryView
        text={errorText(patients.error ?? transplants.error)}
        onRetry={() => void (patients.data ? transplants.refetch() : patients.refetch())}
      />
    );
  }
  return <TransplantForm patientId={own.id} transplant={transplant} />;
}

/** Every section at once; the whole record is saved (PUT), fields not shown are kept. */
function TransplantForm({ patientId, transplant }: { patientId: string; transplant: Transplant }) {
  const t = useTranslations("app.transplant");
  const tc = useTranslations("app.common");
  const router = useRouter();
  const errorText = useErrorText();
  const update = useUpdateTransplant(patientId, transplant.id);
  const remove = useDeleteTransplant(patientId, transplant.id);
  const [draft, setDraft] = useState<Draft>(() => draftFrom(transplant));
  const [saved, setSaved] = useState<Draft>(() => draftFrom(transplant));
  const [tried, setTried] = useState(false);
  const change = (patch: Partial<Draft>) => setDraft((d) => ({ ...d, ...patch }));
  const since = elapsedText(t, transplant);
  const dirty = JSON.stringify(draft) !== JSON.stringify(saved);
  // Leaving with unsaved changes asks first (a long form: one back gesture must not lose it).
  const allowLeaving = usePreventRemove(dirty, ({ repeat }) =>
    Alert.alert(t("unsavedTitle"), t("unsavedBody"), [
      { text: tc("cancel"), style: "cancel" },
      {
        text: t("discard"),
        style: "destructive",
        onPress: () => {
          allowLeaving();
          repeat();
        },
      },
    ]),
  );

  const save = () => {
    const fields = toFields(draft, transplant);
    if (!fields) {
      setTried(true);
      // the fields are far above the button: say so here, and to a screen reader
      AccessibilityInfo.announceForAccessibility(t("fixErrors"));
      return;
    }
    update.mutate(fields, { onSuccess: () => setSaved(draft) });
  };

  const confirmDelete = () =>
    Alert.alert(
      t("deleteConfirmTitle"),
      t("deleteConfirmBody"),
      [
        { text: tc("cancel"), style: "cancel" },
        {
          text: t("delete"),
          style: "destructive",
          onPress: () =>
            remove.mutate(undefined, {
              onSuccess: () => {
                allowLeaving();
                router.back();
              },
            }),
        },
      ],
      { cancelable: true },
    );

  return (
    <Screen>
      {since && <Paragraph muted>{since}</Paragraph>}
      <OrganSection draft={draft} onChange={change} />
      {tried && !stepComplete("organ", draft) && (
        <FormMessage kind="error" text={t("organ.required")} />
      )}
      <DateSection draft={draft} onChange={change} showErrors={tried} />
      {tried && draft.precision === "day" && !stepComplete("date", draft) && (
        <FormMessage kind="error" text={t("date.required")} />
      )}
      <PlaceSection draft={draft} onChange={change} recentHospitals={[]} showErrors={tried} />
      <DonorSection draft={draft} onChange={change} />
      <ExtraSection draft={draft} onChange={change} />
      {tried && !toFields(draft, transplant) && <FormMessage kind="error" text={t("fixErrors")} />}
      {update.isError && <FormMessage kind="error" text={errorText(update.error)} />}
      {update.isSuccess && !dirty && <FormMessage kind="success" text={tc("saved")} />}
      <Button label={tc("save")} onPress={save} busy={update.isPending} />
      <Button
        label={t("delete")}
        variant="danger"
        onPress={confirmDelete}
        busy={remove.isPending}
      />
      {remove.isError && <FormMessage kind="error" text={errorText(remove.error)} />}
    </Screen>
  );
}
