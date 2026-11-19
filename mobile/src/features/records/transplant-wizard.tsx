import { fontSize, space } from "@labtrack/shared";
import { useEffect, useRef, useState } from "react";
import { AccessibilityInfo, Alert, StyleSheet, View } from "react-native";
import { useTranslations } from "use-intl";
import { Text } from "@/components/app-text";

import { Button } from "@/components/button";
import { FormMessage } from "@/components/form-message";
import { Screen, type ScreenScroll } from "@/components/screen";
import { Paragraph } from "@/components/text";
import { useMe } from "@/features/me/use-me";
import { newClientId } from "@/lib/random";
import { useErrorText } from "@/lib/use-error-text";
import { usePalette } from "@/theme/use-palette";

import {
  type Draft,
  emptyDraft,
  STEPS,
  type Step,
  stepComplete,
  toFields,
} from "./transplant-draft";
import {
  DateSection,
  DonorSection,
  ExtraSection,
  OrganSection,
  PlaceSection,
} from "./transplant-sections";
import { ownProfile, useCreateOwnProfile, usePatients } from "./use-profile";
import { useCreateTransplant, useTransplants } from "./use-transplants";

/**
 * The transplant wizard (docs/08, ≤ 3 minutes): organ → date → place → donor, then save - or
 * add the optional details first - then "another transplant?". Only organ, date, country and
 * hospital are needed. The own profile is created on the first save, or on skipping (the
 * first-sign-in wizard only: `canSkip`).
 */
export function TransplantWizard({
  onDone,
  canSkip = false,
}: {
  onDone: () => void;
  canSkip?: boolean;
}) {
  const t = useTranslations("app.transplant");
  const tc = useTranslations("app.common");
  const ts = useTranslations("status");
  const p = usePalette();
  const errorText = useErrorText();
  const me = useMe();
  const patients = usePatients();
  const createProfile = useCreateOwnProfile();
  const own = ownProfile(patients.data);
  const transplants = useTransplants(own?.id);
  const [patientId, setPatientId] = useState<string | undefined>(own?.id);
  const create = useCreateTransplant();
  const [draft, setDraft] = useState<Draft>(() => emptyDraft());
  const [index, setIndex] = useState(0);
  const [asked, setAsked] = useState(false); // "another transplant?" is showing
  const [tried, setTried] = useState(false); // show what is missing after a press
  const scroll = useRef<ScreenScroll>(null);
  // one client_id per record being entered: a retried save finds it instead of duplicating
  const clientId = useRef(newClientId());
  // What the last failed save sent: if the user changes the record before retrying, the first
  // attempt may have been stored anyway (its answer lost) - the retry is then a new record id,
  // or the server would answer with the old content and the change would be lost.
  const lastFailed = useRef<string | null>(null);

  const step: Step = STEPS[index] ?? "organ";
  const change = (patch: Partial<Draft>) => setDraft((d) => ({ ...d, ...patch }));
  const recentHospitals = [...new Set((transplants.data ?? []).map((x) => x.hospital))];
  const busy = createProfile.isPending || create.isPending;
  // the own profile is named as the account: wait for it (never a placeholder name)
  const waiting = !me.data;
  const failure = createProfile.error ?? create.error;

  // A new step starts at the top, and a screen reader hears which step and its question (not
  // on the first render, where the screen title is read; not when only the language changes).
  const announce = useRef<(at: number) => void>(() => undefined);
  announce.current = (at: number) => {
    const name = STEPS[at] ?? "organ";
    AccessibilityInfo.announceForAccessibility(
      `${t("step", { current: at + 1, total: STEPS.length })}. ${t(`${name}.question`)}`,
    );
  };
  const firstRender = useRef(true);
  useEffect(() => {
    scroll.current?.scrollTo({ y: 0, animated: false });
    if (firstRender.current) {
      firstRender.current = false;
      return;
    }
    announce.current(index);
  }, [index]);

  async function profileId(): Promise<string> {
    const existing = patientId ?? own?.id;
    if (existing) return existing;
    if (!me.data) throw new Error("account not loaded");
    const created = await createProfile.mutateAsync(me.data.display_name);
    setPatientId(created.id);
    return created.id;
  }

  async function skipNow() {
    try {
      await profileId();
      onDone();
    } catch {
      // shown below (createProfile.error)
    }
  }

  const filled = draft.organ !== null || draft.hospital.trim() !== "" || draft.day !== null;
  const skip = () => {
    if (!filled) {
      void skipNow();
      return;
    }
    Alert.alert(
      t("skipConfirmTitle"),
      t("skipConfirmBody"),
      [
        { text: tc("cancel"), style: "cancel" },
        { text: t("skipConfirm"), style: "destructive", onPress: () => void skipNow() },
      ],
      { cancelable: true },
    );
  };

  async function save() {
    const fields = toFields(draft);
    if (!fields) {
      setTried(true);
      setIndex(
        Math.max(
          0,
          STEPS.findIndex((s) => !stepComplete(s, draft)),
        ),
      );
      return;
    }
    const sent = JSON.stringify(fields);
    if (lastFailed.current !== null && lastFailed.current !== sent) {
      clientId.current = newClientId();
    }
    try {
      const id = await profileId();
      await create.mutateAsync({ patientId: id, body: { ...fields, client_id: clientId.current } });
      lastFailed.current = null;
      setAsked(true);
    } catch {
      lastFailed.current = sent; // shown below
    }
  }

  function next() {
    if (!stepComplete(step, draft)) {
      setTried(true);
      return;
    }
    setTried(false);
    setIndex(index + 1);
  }

  function another() {
    clientId.current = newClientId();
    lastFailed.current = null;
    setDraft((d) => ({ ...emptyDraft(d.transplantNumber + 1), country: d.country }));
    setIndex(0);
    setTried(false);
    setAsked(false);
    announce.current(0); // index may already be 0: the effect would not run
  }

  if (asked) {
    return (
      <Screen>
        <FormMessage kind="success" text={t("saved")} />
        <Paragraph>{t("anotherQuestion")}</Paragraph>
        <Button label={t("anotherYes")} variant="secondary" onPress={another} />
        <Button label={t("anotherNo")} onPress={onDone} />
      </Screen>
    );
  }

  const missing = tried && !stepComplete(step, draft);
  return (
    <Screen scrollRef={scroll}>
      {index === 0 && <Paragraph>{t("wizardIntro")}</Paragraph>}
      <Text style={[styles.step, { color: p.textMuted }]}>
        {t("step", { current: index + 1, total: STEPS.length })}
      </Text>
      {step === "organ" && <OrganSection draft={draft} onChange={change} />}
      {step === "date" && <DateSection draft={draft} onChange={change} showErrors={tried} />}
      {step === "place" && (
        <PlaceSection
          draft={draft}
          onChange={change}
          recentHospitals={recentHospitals}
          showErrors={tried}
        />
      )}
      {step === "donor" && <DonorSection draft={draft} onChange={change} />}
      {step === "extra" && <ExtraSection draft={draft} onChange={change} />}
      {missing && step === "organ" && <FormMessage kind="error" text={t("organ.required")} />}
      {missing && step === "date" && draft.precision === "day" && (
        <FormMessage kind="error" text={t("date.required")} />
      )}
      {failure && <FormMessage kind="error" text={errorText(failure)} />}
      {me.isError && !me.data && (
        <>
          <FormMessage kind="error" text={errorText(me.error)} />
          <Button label={ts("retry")} variant="secondary" onPress={() => void me.refetch()} />
        </>
      )}
      <View style={styles.actions}>
        {step === "donor" || step === "extra" ? (
          <Button label={t("saveNow")} onPress={() => void save()} busy={busy} disabled={waiting} />
        ) : (
          <Button label={t("next")} onPress={next} />
        )}
        {step === "donor" && (
          <Button label={t("addMore")} variant="secondary" onPress={next} disabled={busy} />
        )}
        {index > 0 && (
          <Button label={t("back")} variant="secondary" onPress={() => setIndex(index - 1)} />
        )}
        {canSkip && (
          <>
            <Button label={t("skip")} variant="link" onPress={skip} disabled={busy || waiting} />
            <Text style={[styles.hint, { color: p.textMuted }]}>{t("skipHint")}</Text>
          </>
        )}
      </View>
    </Screen>
  );
}

const styles = StyleSheet.create({
  step: { fontSize: fontSize.caption },
  actions: { gap: space.sm },
  hint: { fontSize: fontSize.caption, lineHeight: fontSize.caption * 1.4 },
});
