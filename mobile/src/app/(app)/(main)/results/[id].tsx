import { useLocalSearchParams, useRouter } from "expo-router";
import { useState } from "react";
import { Alert, View } from "react-native";
import { useTranslations } from "use-intl";

import { Button } from "@/components/button";
import { SelectList } from "@/components/choices";
import { FormMessage } from "@/components/form-message";
import { Screen } from "@/components/screen";
import { LoadingView, RetryView } from "@/components/state-view";
import { Paragraph, Title } from "@/components/text";
import { useRecordProfile } from "@/features/health/record-screens";
import { ReportReview } from "@/features/review/report-review";
import { useMoveDocument, useReport } from "@/features/review/use-review";
import { useDocumentReports } from "@/features/upload/use-reports";
import { useErrorText } from "@/lib/use-error-text";

/**
 * Review of what was read from one document (Phase 5.5) - or of one typed-in report: a
 * notice names either (review_ready: the document, critical_pending of a typed-in report:
 * the report), so the id is tried as a document first. Drafts are checked and confirmed here;
 * confirmed reports are shown as they are. Nothing is computed in the app (rule 6).
 */
export default function ReviewScreen() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const t = useTranslations("app.upload.review");
  const tu = useTranslations("app.upload");
  const errorText = useErrorText();
  const router = useRouter();
  const { patients, own } = useRecordProfile();
  const reports = useDocumentReports(own?.id, id);
  const notDocument = reports.isError;
  const single = useReport(own?.id, id, notDocument);
  const move = useMoveDocument(own?.id, id);
  const [moving, setMoving] = useState(false);
  const [target, setTarget] = useState<string | null>(null);

  if (!own && !patients.isPending) {
    return (
      <Screen>
        <Paragraph>{tu("noProfile")}</Paragraph>
      </Screen>
    );
  }
  if (!own || reports.isPending || (notDocument && single.isPending)) return <LoadingView />;
  const list = reports.data ?? (single.data ? [single.data] : undefined);
  if (!list) {
    return (
      <RetryView
        text={errorText(single.error ?? reports.error)}
        onRetry={() => void (notDocument ? single.refetch() : reports.refetch())}
      />
    );
  }
  const drafts = list.filter((r) => r.status === "needs_review");
  const byAi = list.some((r) => r.method === "ai");
  // only the owner moves a document (0037); to another profile the user writes
  const others = (patients.data ?? []).filter(
    (x) => x.id !== own.id && (x.access_level === "owner" || x.access_level === "caregiver"),
  );
  const canMove = reports.data !== undefined && own.access_level === "owner" && drafts.length > 0;
  const moveTo = () => {
    const name = others.find((x) => x.id === target)?.full_name;
    if (!target || !name) return;
    // someone's health data changes person: always confirmed first (UI review M2)
    Alert.alert(t("move"), t("moveConfirm", { name }), [
      { text: t("cancel"), style: "cancel" },
      {
        text: t("move"),
        onPress: () => move.mutate(target, { onSuccess: () => router.replace("/results") }),
      },
    ]);
  };
  return (
    <Screen testID="document-reports">
      <Title>{t("title")}</Title>
      <Paragraph muted>{own.full_name}</Paragraph>
      {drafts.some((r) => r.source === "read") && (
        <FormMessage kind="warning" quiet text={t("draftNotice")} />
      )}
      {drafts.some((r) => r.source === "typed") && (
        <FormMessage kind="warning" quiet text={t("typedNotice")} />
      )}
      {byAi && <FormMessage kind="warning" quiet text={t("byAi")} />}
      {moving && (
        // at the top, where the person is reading: the choice of profile, then "Шилжүүлэх"
        <View testID="move-picker">
          {others.length === 0 ? (
            <Paragraph>{t("noOtherProfile")}</Paragraph>
          ) : (
            <>
              <SelectList
                label={t("moveTo")}
                options={others.map((x) => x.id)}
                value={target}
                labelOf={(pid) => others.find((x) => x.id === pid)?.full_name ?? ""}
                onSelect={setTarget}
              />
              <Button
                label={t("move")}
                disabled={target === null}
                busy={move.isPending}
                onPress={moveTo}
              />
            </>
          )}
          {move.error && <FormMessage kind="error" text={errorText(move.error)} />}
          <Button label={t("cancel")} variant="link" onPress={() => setMoving(false)} />
        </View>
      )}
      {list.length === 0 ? (
        <Paragraph>{t("empty")}</Paragraph>
      ) : (
        list.map((r) => (
          <ReportReview
            key={r.id}
            patientId={own.id}
            profileName={own.full_name}
            report={r}
            onMove={canMove ? () => setMoving(true) : undefined}
          />
        ))
      )}
    </Screen>
  );
}
