import { Host, Switch } from "@expo/ui";
import { fontSize, space } from "@labtrack/shared";
import { useRef, useState } from "react";
import { StyleSheet, Text, View } from "react-native";
import { useTranslations } from "use-intl";
import { Button } from "@/components/button";
import { Choices } from "@/components/choices";
import { dayOf, PickerField } from "@/components/date-field";
import { FormMessage } from "@/components/form-message";
import { Screen, type ScreenScroll } from "@/components/screen";
import { TextField } from "@/components/text-field";
import { ProfileBanner } from "@/features/records/profile-banner";
import { newClientId } from "@/lib/random";
import { useErrorText } from "@/lib/use-error-text";
import { usePalette } from "@/theme/use-palette";

import {
  createBody,
  emptyMedDraft,
  hasErrors,
  type MedDraft,
  type ScheduleErrors,
  scheduleErrors,
} from "./med-draft";
import { ScheduleEditor } from "./schedule-editor";
import { type CatalogItem, useCatalogSearch, useCreateMedication } from "./use-medications";

const YEAR_MS = 365 * 24 * 60 * 60_000;

/**
 * Add a medicine: find it in the catalog (Mongolian, English, brand) or type it, then the
 * dose per time as the doctor instructed. A retried save of the same entry sends the same
 * client_ids (no duplicate); a changed entry gets new ones.
 */
export function MedicationForm({ patientId, onDone }: { patientId: string; onDone: () => void }) {
  const t = useTranslations("app.meds");
  const p = usePalette();
  const errorText = useErrorText();
  const scroll = useRef<ScreenScroll>(null);
  const today = dayOf(new Date());
  const [draft, setDraft] = useState<MedDraft>(() => emptyMedDraft(today));
  const [query, setQuery] = useState("");
  const [manual, setManual] = useState(false);
  const [more, setMore] = useState(false);
  const [showErrors, setShowErrors] = useState(false);
  const sent = useRef<{ key: string; ids: [string, string] } | null>(null);
  const create = useCreateMedication();
  const catalog = useCatalogSearch(manual || draft.catalogCode ? "" : query);

  const set = (patch: Partial<MedDraft>) => setDraft((d) => ({ ...d, ...patch }));
  const errors: ScheduleErrors = scheduleErrors(draft.schedule);
  const nameMissing = draft.name.trim() === "";
  const invalid = nameMissing || hasErrors(errors);

  const choose = (item: CatalogItem) =>
    set({ catalogCode: item.code, name: item.generic_mn, form: item.forms[0] ?? draft.form });

  const save = () => {
    setShowErrors(true);
    if (invalid) {
      scroll.current?.scrollTo({ y: 0, animated: true });
      return;
    }
    const key = JSON.stringify(draft);
    if (sent.current?.key !== key) sent.current = { key, ids: [newClientId(), newClientId()] };
    const [id, regimenId] = sent.current.ids;
    create.mutate(
      { patientId, body: createBody(draft, id, regimenId, today) },
      { onSuccess: onDone },
    );
  };

  return (
    <Screen scrollRef={scroll}>
      <ProfileBanner />
      <Text style={[styles.note, { color: p.textMuted }]}>{t("form.disclaimer")}</Text>
      {showErrors && invalid && <FormMessage kind="error" text={t("form.errors.summary")} />}
      {create.error && <FormMessage kind="error" text={errorText(create.error)} />}

      {draft.catalogCode ? (
        <View style={styles.group}>
          <Text style={[styles.label, { color: p.text }]}>
            {t("form.chosen", { name: draft.name })}
          </Text>
          <Button
            label={t("form.change")}
            variant="link"
            onPress={() => set({ catalogCode: null, name: "" })}
          />
        </View>
      ) : manual ? (
        <TextField
          label={t("form.name")}
          value={draft.name}
          maxLength={200}
          error={showErrors && nameMissing ? t("form.errors.name") : undefined}
          onChangeText={(name) => set({ name })}
        />
      ) : (
        <View style={styles.group}>
          <TextField
            label={t("form.search")}
            hint={t("form.searchHint")}
            value={query}
            maxLength={60}
            autoCorrect={false}
            error={showErrors && nameMissing ? t("form.errors.name") : undefined}
            onChangeText={setQuery}
          />
          {query.trim().length >= 2 && catalog.data && catalog.data.length > 0 && (
            <Text accessibilityLiveRegion="polite" style={[styles.note, { color: p.textMuted }]}>
              {t("form.results", { n: Math.min(catalog.data.length, 8) })}
            </Text>
          )}
          {(catalog.data ?? []).slice(0, 8).map((item) => (
            <Button
              key={item.code}
              label={[item.generic_mn, item.brands.slice(0, 2).join(", ")]
                .filter(Boolean)
                .join(" · ")}
              variant="secondary"
              onPress={() => choose(item)}
            />
          ))}
          {query.trim().length >= 2 && catalog.data?.length === 0 && (
            <Text accessibilityLiveRegion="polite" style={[styles.note, { color: p.textMuted }]}>
              {t("form.searchEmpty")}
            </Text>
          )}
          <Button
            label={t("form.manual")}
            variant="link"
            onPress={() => {
              setManual(true);
              set({ name: query.trim() });
            }}
          />
        </View>
      )}

      <ScheduleEditor
        value={draft.schedule}
        onChange={(schedule) => set({ schedule })}
        errors={showErrors ? errors : null}
      />

      <Button
        label={t("form.more")}
        variant="secondary"
        expanded={more}
        onPress={() => setMore(!more)}
      />
      {more && (
        <>
          <TextField
            label={t("form.brand")}
            value={draft.brand}
            maxLength={200}
            onChangeText={(brand) => set({ brand })}
          />
          <TextField
            label={t("form.form")}
            hint={t("form.formHint")}
            value={draft.form}
            maxLength={200}
            onChangeText={(form) => set({ form })}
          />
          <TextField
            label={t("form.strength")}
            hint={t("form.strengthHint")}
            value={draft.strength}
            maxLength={200}
            onChangeText={(strength) => set({ strength })}
          />
        </>
      )}
      <PickerField
        label={t("form.startedOn")}
        mode="date"
        value={draft.startedOn}
        maximum={new Date()}
        minimum={new Date(1950, 0, 1)}
        onChange={(startedOn) => set({ startedOn })}
      />
      <PickerField
        label={t("form.plannedEnd")}
        mode="date"
        value={draft.plannedEndOn}
        minimum={new Date(`${draft.startedOn ?? today}T12:00:00`)}
        maximum={new Date(Date.now() + YEAR_MS)}
        onChange={(plannedEndOn) => set({ plannedEndOn })}
      />
      {draft.plannedEndOn && (
        <Button
          label={t("form.plannedEndClear")}
          variant="link"
          onPress={() => set({ plannedEndOn: null })}
        />
      )}

      <Host matchContents={{ vertical: true }} style={styles.wide}>
        <Switch
          label={t("form.reminders")}
          value={draft.remindersEnabled}
          onValueChange={(remindersEnabled) => set({ remindersEnabled })}
          testID="med-reminders"
        />
      </Host>
      <Choices
        label={t("form.tzMode")}
        options={["home", "local"] as const}
        value={draft.timezoneMode}
        labelOf={(m) => t(m === "home" ? "form.tzHome" : "form.tzLocal")}
        onSelect={(timezoneMode) => set({ timezoneMode })}
      />
      <Text style={[styles.note, { color: p.textMuted }]}>{t("form.tzHint")}</Text>

      <Button label={t("form.save")} busy={create.isPending} onPress={save} />
    </Screen>
  );
}

const styles = StyleSheet.create({
  group: { gap: space.sm },
  wide: { alignSelf: "stretch" },
  label: { fontSize: fontSize.body, fontWeight: "600" },
  note: { fontSize: fontSize.body, lineHeight: fontSize.body * 1.4 },
});
