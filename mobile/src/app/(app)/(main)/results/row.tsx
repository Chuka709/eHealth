import { useLocalSearchParams, useRouter } from "expo-router";
import { useState } from "react";
import { useTranslations } from "use-intl";

import { Button } from "@/components/button";
import { SelectList } from "@/components/choices";
import { FormMessage } from "@/components/form-message";
import { Screen } from "@/components/screen";
import { LoadingView, RetryView } from "@/components/state-view";
import { Paragraph, Title } from "@/components/text";
import { TextField } from "@/components/text-field";
import { useRecordProfile } from "@/features/health/record-screens";
import {
  type ResultPatch,
  useLabTests,
  useReport,
  useReviewActions,
} from "@/features/review/use-review";
import { useErrorText } from "@/lib/use-error-text";

type Field = "raw_unit" | "ref_text" | "critical_text";
const NO_TEST = "";

/**
 * One row of a draft, corrected or added by the person (Phase 5.5): the text as printed and,
 * when the name was not recognised, the test it means. The server recomputes the row
 * (rule 6); what was read before a change is kept and shown as "corrected" (medical review).
 */
export default function ResultRowScreen() {
  const params = useLocalSearchParams<{ report: string; row?: string }>();
  const t = useTranslations("app.upload.review");
  const errorText = useErrorText();
  const router = useRouter();
  const { own } = useRecordProfile();
  const report = useReport(own?.id, params.report);
  const tests = useLabTests();
  const actions = useReviewActions(own?.id, params.report);
  const row = report.data?.results.find((x) => x.id === params.row);
  const adding = params.row === undefined;
  const [name, setName] = useState("");
  const [value, setValue] = useState<string | null>(null);
  const [unit, setUnit] = useState<string | null>(null);
  const [ref, setRef] = useState<string | null>(null);
  const [critical, setCritical] = useState<string | null>(null);
  const [test, setTest] = useState<string | null>(null);
  const [missing, setMissing] = useState(false);

  if (report.isPending) return <LoadingView />;
  if (!report.data || (!adding && !row)) {
    return <RetryView text={errorText(report.error)} onRetry={() => void report.refetch()} />;
  }
  const shown = {
    value: value ?? row?.raw_value ?? "",
    unit: unit ?? row?.raw_unit ?? "",
    ref: ref ?? row?.ref_text ?? "",
    critical: critical ?? row?.critical_text ?? "",
    test: test ?? row?.test_code ?? NO_TEST,
  };
  const saving = actions.editResult.isPending || actions.addResult.isPending;
  const failure = actions.editResult.error ?? actions.addResult.error;
  const done = { onSuccess: () => router.back() };

  const save = () => {
    if (!shown.value.trim() || (adding && !name.trim())) {
      setMissing(true);
      return;
    }
    if (adding) {
      actions.addResult.mutate(
        {
          raw_name: name.trim(),
          raw_value: shown.value.trim(),
          ...(shown.unit.trim() ? { raw_unit: shown.unit.trim() } : {}),
          ...(shown.ref.trim() ? { ref_text: shown.ref.trim() } : {}),
          ...(shown.critical.trim() ? { critical_text: shown.critical.trim() } : {}),
          ...(shown.test ? { test_code: shown.test } : {}),
        },
        done,
      );
      return;
    }
    if (!row) return;
    const patch: ResultPatch = {};
    const clear: Field[] = [];
    if (shown.value.trim() !== row.raw_value) patch.raw_value = shown.value.trim();
    const texts: [Field, string, string | null][] = [
      ["raw_unit", shown.unit, row.raw_unit],
      ["ref_text", shown.ref, row.ref_text],
      ["critical_text", shown.critical, row.critical_text],
    ];
    for (const [field, now, before] of texts) {
      if (now.trim() === (before ?? "")) continue;
      if (now.trim()) patch[field] = now.trim();
      else clear.push(field);
    }
    if (clear.length > 0) patch.clear = clear;
    if (shown.test && shown.test !== (row.test_code ?? NO_TEST)) patch.test_code = shown.test;
    if (Object.keys(patch).length === 0) {
      router.back();
      return;
    }
    actions.editResult.mutate({ resultId: row.id, patch }, done);
  };

  const testCodes = [NO_TEST, ...(tests.data ?? []).map((x) => x.code)];
  return (
    <Screen testID="result-row">
      <Title>{adding ? t("newRowTitle") : t("rowTitle")}</Title>
      {adding ? (
        <TextField
          label={t("name")}
          value={name}
          onChangeText={setName}
          maxLength={200}
          error={missing && !name.trim() ? t("required") : undefined}
          testID="row-name"
        />
      ) : (
        <Paragraph>{row?.raw_name}</Paragraph>
      )}
      <TextField
        label={t("value")}
        value={shown.value}
        onChangeText={setValue}
        maxLength={200}
        error={missing && !shown.value.trim() ? t("required") : undefined}
        testID="row-value"
      />
      <TextField
        label={t("unit")}
        value={shown.unit}
        onChangeText={setUnit}
        maxLength={50}
        testID="row-unit"
      />
      <TextField
        label={t("ref")}
        value={shown.ref}
        onChangeText={setRef}
        maxLength={300}
        testID="row-ref"
      />
      <TextField
        label={t("criticalField")}
        value={shown.critical}
        onChangeText={setCritical}
        maxLength={300}
        testID="row-critical"
      />
      {tests.data && (
        <SelectList
          label={t("testPick")}
          options={testCodes}
          value={shown.test}
          labelOf={(code) =>
            code === NO_TEST
              ? t("testNone")
              : (tests.data.find((x) => x.code === code)?.name_mn ?? code)
          }
          onSelect={setTest}
          testID="row-test"
        />
      )}
      {failure && <FormMessage kind="error" text={errorText(failure)} />}
      <Button label={t("save")} busy={saving} onPress={save} />
    </Screen>
  );
}
