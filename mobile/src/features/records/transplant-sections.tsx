import DateTimePicker from "@expo/ui/community/datetime-picker";
import { fontSize, space } from "@labtrack/shared";
import { useState } from "react";
import { Platform, StyleSheet, View } from "react-native";
import { useTranslations } from "use-intl";
import { Text } from "@/components/app-text";

import { Button } from "@/components/button";
import { Choices, SelectList } from "@/components/choices";
import { TextField } from "@/components/text-field";
import { formatDate } from "@/lib/dates";
import { usePalette } from "@/theme/use-palette";

import {
  BLOOD_TYPES,
  COUNTRIES,
  DONOR_TYPES,
  type Draft,
  FIRST_YEAR,
  ORGANS,
  type Precision,
  SEROSTATUS,
  type Serostatus,
  yearInRange,
} from "./transplant-draft";

type SectionProps = { draft: Draft; onChange: (patch: Partial<Draft>) => void };

export function OrganSection({ draft, onChange }: SectionProps) {
  const t = useTranslations("app.transplant");
  return (
    <>
      <Choices
        label={t("organ.question")}
        options={ORGANS}
        value={draft.organ}
        labelOf={(o) => t(`organ.${o}`)}
        onSelect={(organ) => onChange({ organ })}
        columns={2}
      />
      <TextField
        label={t("organ.detail")}
        hint={t("organ.detailHint")}
        value={draft.organDetail}
        onChangeText={(organDetail) => onChange({ organDetail })}
        maxLength={200}
      />
    </>
  );
}

const MONTHS = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12] as const;
const pad = (n: number) => String(n).padStart(2, "0");

export function DateSection({
  draft,
  onChange,
  showErrors = false,
}: SectionProps & { showErrors?: boolean }) {
  const t = useTranslations("app.transplant");
  const p = usePalette();
  const [picking, setPicking] = useState(false);
  const [yearText, setYearText] = useState(draft.year === null ? "" : String(draft.year));
  const today = new Date();
  const picked = draft.day ? new Date(`${draft.day}T12:00:00`) : today;
  const setPrecision = (precision: Precision) =>
    onChange({ precision, month: precision === "month" ? (draft.month ?? null) : null });
  const pick = (date: Date) =>
    onChange({ day: `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}` });
  const yearError =
    showErrors && draft.precision !== "day" && !yearInRange(draft.year)
      ? t("date.yearInvalid", { from: FIRST_YEAR, to: today.getFullYear() })
      : undefined;

  return (
    <>
      <Text style={[styles.question, { color: p.text }]} accessibilityRole="header">
        {t("date.question")}
      </Text>
      <Choices
        label={t("date.precision")}
        options={["day", "month", "year"] as const}
        value={draft.precision}
        labelOf={(prec) => t(`date.${prec}`)}
        onSelect={setPrecision}
      />
      {draft.precision === "day" && (
        <>
          <Button
            label={
              draft.day
                ? t("date.picked", { date: formatDate(`${draft.day}T12:00:00Z`) })
                : t("date.pick")
            }
            variant="secondary"
            onPress={() => setPicking(!picking)}
            expanded={picking}
          />
          {picking && (
            <DateTimePicker
              value={picked}
              mode="date"
              presentation="dialog"
              maximumDate={today}
              minimumDate={new Date(FIRST_YEAR, 0, 1)}
              onValueChange={(_, date) => {
                pick(date);
                // Android: a dialog, done once a date is chosen. iOS: inline - every tap
                // (month, day) changes the value, so it stays open until "Done".
                if (Platform.OS === "android") setPicking(false);
              }}
              onDismiss={() => setPicking(false)}
            />
          )}
          {picking && Platform.OS === "ios" && (
            <Button label={t("date.done")} onPress={() => setPicking(false)} />
          )}
        </>
      )}
      {draft.precision !== "day" && (
        <TextField
          label={t("date.year_label")}
          hint={t("date.yearHint")}
          value={yearText}
          keyboardType="number-pad"
          maxLength={4}
          error={yearError}
          onChangeText={(text) => {
            const digits = text.replace(/\D/g, "").slice(0, 4);
            setYearText(digits);
            onChange({ year: digits.length === 4 ? Number(digits) : null });
          }}
        />
      )}
      {draft.precision === "month" && (
        <SelectList
          label={t("date.month_label")}
          options={MONTHS}
          value={(draft.month as (typeof MONTHS)[number] | null) ?? null}
          labelOf={(n) => t("date.monthName", { n })}
          onSelect={(month) => onChange({ month })}
          testID="transplant-month"
        />
      )}
    </>
  );
}

const OTHER = "other";

export function PlaceSection({
  draft,
  onChange,
  recentHospitals,
  showErrors = false,
}: SectionProps & { recentHospitals: readonly string[]; showErrors?: boolean }) {
  const t = useTranslations("app.transplant");
  const p = usePalette();
  const listed = (COUNTRIES as readonly string[]).includes(draft.country);
  const [other, setOther] = useState(!listed);
  const countryLabel = (c: string) => (c === OTHER ? t("place.otherCountry") : t(`country.${c}`));
  return (
    <>
      <Text style={[styles.question, { color: p.text }]} accessibilityRole="header">
        {t("place.question")}
      </Text>
      <SelectList
        label={t("place.country")}
        options={[...COUNTRIES, OTHER] as readonly string[]}
        value={other ? OTHER : draft.country}
        labelOf={countryLabel}
        onSelect={(c) => {
          const isOther = c === OTHER;
          setOther(isOther);
          onChange({ country: isOther ? "" : c });
        }}
        testID="transplant-country"
      />
      {other && (
        <TextField
          label={t("place.countryCode")}
          hint={t("place.countryCodeHint")}
          value={draft.country}
          autoCapitalize="characters"
          autoCorrect={false}
          maxLength={2}
          error={
            showErrors && !/^[A-Z]{2}$/.test(draft.country)
              ? t("place.countryCodeInvalid")
              : undefined
          }
          onChangeText={(code) => onChange({ country: code.toUpperCase().replace(/[^A-Z]/g, "") })}
        />
      )}
      <TextField
        label={t("place.city")}
        value={draft.city}
        onChangeText={(city) => onChange({ city })}
        maxLength={200}
      />
      <TextField
        label={t("place.hospital")}
        value={draft.hospital}
        onChangeText={(hospital) => onChange({ hospital })}
        error={showErrors && !draft.hospital.trim() ? t("place.hospitalRequired") : undefined}
        maxLength={200}
      />
      {recentHospitals.length > 0 && (
        <View style={styles.group}>
          <Text style={[styles.label, { color: p.text }]}>{t("place.recent")}</Text>
          {recentHospitals.map((h) => (
            <Button key={h} label={h} variant="link" onPress={() => onChange({ hospital: h })} />
          ))}
        </View>
      )}
    </>
  );
}

export function DonorSection({ draft, onChange }: SectionProps) {
  const t = useTranslations("app.transplant");
  return (
    <>
      <Choices
        label={t("donor.question")}
        options={DONOR_TYPES}
        value={draft.donorType}
        labelOf={(d) => t(`donor.${d}`)}
        onSelect={(donorType) => onChange({ donorType })}
      />
      {draft.donorType.startsWith("living") && (
        <TextField
          label={t("donor.relation")}
          hint={t("donor.relationHint")}
          value={draft.donorRelation}
          onChangeText={(donorRelation) => onChange({ donorRelation })}
          maxLength={200}
        />
      )}
    </>
  );
}

export function ExtraSection({ draft, onChange }: SectionProps) {
  const t = useTranslations("app.transplant");
  const p = usePalette();
  const bloodLabel = (b: string) => (b === "unknown" ? t("extra.unknown") : b);
  const sero = (key: "cmvDonor" | "cmvRecipient") => (
    <Choices
      label={t(`extra.${key}`)}
      options={SEROSTATUS}
      value={draft[key]}
      labelOf={(s: Serostatus) => t(`extra.${s}`)}
      onSelect={(value) => onChange({ [key]: draft[key] === value ? null : value })}
    />
  );
  const field = (
    key:
      | "hlaMismatch"
      | "inductionTherapy"
      | "primaryDisease"
      | "preTransplantDialysis"
      | "followUpCenter"
      | "followUpDoctor",
    label: string,
  ) => (
    <TextField
      label={label}
      value={draft[key]}
      onChangeText={(value) => onChange({ [key]: value })}
      maxLength={200}
    />
  );
  return (
    <>
      <Text style={[styles.question, { color: p.text }]} accessibilityRole="header">
        {t("extra.question")}
      </Text>
      <Text style={[styles.note, { color: p.textMuted }]}>{t("extra.intro")}</Text>
      <SelectList
        label={t("extra.recipientBlood")}
        options={BLOOD_TYPES}
        value={draft.recipientBloodType}
        labelOf={bloodLabel}
        onSelect={(recipientBloodType) => onChange({ recipientBloodType })}
      />
      <SelectList
        label={t("extra.donorBlood")}
        options={BLOOD_TYPES}
        value={draft.donorBloodType}
        labelOf={bloodLabel}
        onSelect={(donorBloodType) => onChange({ donorBloodType })}
      />
      {sero("cmvDonor")}
      {sero("cmvRecipient")}
      {field("hlaMismatch", t("extra.hla"))}
      {field("inductionTherapy", t("extra.induction"))}
      {field("primaryDisease", t("extra.primaryDisease"))}
      {field("preTransplantDialysis", t("extra.dialysis"))}
      {field("followUpCenter", t("extra.followUpCenter"))}
      {field("followUpDoctor", t("extra.followUpDoctor"))}
      <TextField
        label={t("extra.notes")}
        value={draft.notes}
        onChangeText={(notes) => onChange({ notes })}
        maxLength={4000}
        multiline
      />
    </>
  );
}

const styles = StyleSheet.create({
  group: { gap: space.sm },
  choices: { gap: space.sm },
  grid: { flexDirection: "row", flexWrap: "wrap", gap: space.sm },
  full: { alignSelf: "stretch" },
  // two per row; each still a full-height touch target that grows with the font size
  half: { flexBasis: "47%", flexGrow: 1 },
  label: { fontSize: fontSize.body, fontWeight: "600" },
  question: { fontSize: fontSize.bodyLarge, fontWeight: "700" },
  note: { fontSize: fontSize.body, lineHeight: fontSize.body * 1.4 },
});
