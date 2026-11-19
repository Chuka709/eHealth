import { useState } from "react";
import { useTranslations } from "use-intl";

import { Button } from "@/components/button";
import { FormMessage } from "@/components/form-message";
import { Screen } from "@/components/screen";
import { Segmented } from "@/components/segmented";
import { LoadingView, RetryView } from "@/components/state-view";
import { Paragraph, Title } from "@/components/text";
import { type ExportKind, useExportFile } from "@/features/exports/use-exports";
import { useRecordProfile } from "@/features/health/record-screens";
import { usePinnedProfile } from "@/features/records/active-profile";
import { ProfileBanner } from "@/features/records/profile-banner";
import { ProfileChanged } from "@/features/records/profile-changed";
import { useLocale } from "@/lib/i18n";
import { useErrorText } from "@/lib/use-error-text";

const MONTHS = ["3", "6", "12"] as const;
const LANGS = ["mn", "en"] as const;

/**
 * The doctor's summary PDF for anyone who reads the profile, and the owner's full data export
 * (JSON, FHIR) - Phase 7.6. Each file goes straight to the share sheet (print, Files, mail):
 * the app keeps no copy beyond the fixed export folder, emptied on sign-out.
 */
export default function SummaryScreen() {
  const t = useTranslations("app.summaryExport");
  const errorText = useErrorText();
  const appLocale = useLocale();
  const { patients, own: active } = useRecordProfile();
  const { pinned: own, changed } = usePinnedProfile(active);
  const file = useExportFile(own?.id ?? "");
  const [months, setMonths] = useState<(typeof MONTHS)[number]>("6");
  const [lang, setLang] = useState<(typeof LANGS)[number]>(appLocale === "en" ? "en" : "mn");
  const [last, setLast] = useState<ExportKind | null>(null);

  if (changed) return <ProfileChanged />;
  if (patients.isPending) return <LoadingView />;
  if (!own) {
    return <RetryView text={errorText(patients.error)} onRetry={() => void patients.refetch()} />;
  }
  const isOwner = own.access_level === "owner";
  const run = (kind: ExportKind) => {
    setLast(kind);
    file.mutate({ kind, months: Number(months), lang });
  };
  const busy = (kind: ExportKind) => file.isPending && last === kind;

  return (
    <Screen>
      <ProfileBanner />
      <Title>{t("summary.title")}</Title>
      <Paragraph>{t("summary.what")}</Paragraph>
      <Segmented
        label={t("summary.months")}
        options={MONTHS}
        value={months}
        labelOf={(m) => t("summary.monthsN", { n: Number(m) })}
        onSelect={setMonths}
        testID="summary-months"
        showLabel
      />
      <Segmented
        label={t("summary.lang")}
        options={LANGS}
        value={lang}
        labelOf={(l) => t(`summary.langs.${l}`)}
        onSelect={setLang}
        testID="summary-lang"
        showLabel
      />
      <Button
        label={t("summary.button")}
        disabled={file.isPending}
        busy={busy("summary")}
        onPress={() => run("summary")}
      />

      {isOwner && (
        <>
          <Title>{t("export.title")}</Title>
          <Paragraph>{t("export.what")}</Paragraph>
          <FormMessage kind="warning" text={t("export.care")} />
          <Button
            variant="secondary"
            label={t("export.json")}
            disabled={file.isPending}
            busy={busy("json")}
            onPress={() => run("json")}
          />
          <Button
            variant="secondary"
            label={t("export.fhir")}
            disabled={file.isPending}
            busy={busy("fhir")}
            onPress={() => run("fhir")}
          />
          <Paragraph muted>{t("export.fhirHint")}</Paragraph>
        </>
      )}

      {file.data === "unavailable" && <FormMessage kind="error" text={t("unavailable")} />}
      {file.isError && <FormMessage kind="error" text={errorText(file.error)} />}
    </Screen>
  );
}
