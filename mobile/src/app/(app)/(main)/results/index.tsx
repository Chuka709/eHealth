import { fontSize, radius, space } from "@labtrack/shared";
import { useRouter } from "expo-router";
import { StyleSheet, View } from "react-native";
import { useTranslations } from "use-intl";

import { Text } from "@/components/app-text";
import { Button } from "@/components/button";
import { FormMessage } from "@/components/form-message";
import { Icon, type IconName } from "@/components/icon";
import { Screen } from "@/components/screen";
import { LoadingView, RetryView } from "@/components/state-view";
import { Paragraph, Title } from "@/components/text";
import { useRecordProfile } from "@/features/health/record-screens";
import { dismissFailedUpload } from "@/features/upload/upload-queue";
import {
  type DocumentItem,
  sendWaitingUploads,
  useDocuments,
  useUploadQueue,
} from "@/features/upload/use-uploads";
import { formatDateTime } from "@/lib/dates";
import { queryClient } from "@/lib/query-client";
import { useErrorText } from "@/lib/use-error-text";
import { usePalette } from "@/theme/use-palette";

const STATUS_ICON: Record<string, IconName> = {
  uploaded: "shield-search",
  queued: "check-circle-outline",
  processing: "progress-clock",
  needs_review: "clipboard-check-outline",
  confirmed: "check-decagram-outline",
  failed: "alert-circle-outline",
  rejected: "close-octagon-outline",
};

/**
 * The profile's lab result files (Phase 3.4): files still on the phone first (waiting for the
 * network, or refused - with why), then what the server has, each with how far it got.
 */
export default function ResultsScreen() {
  const t = useTranslations("app.upload");
  const errorText = useErrorText();
  const router = useRouter();
  const p = usePalette();
  const { own } = useRecordProfile();
  const documents = useDocuments(own?.id);
  const queue = useUploadQueue();
  const waiting = (queue.data?.pending ?? []).filter((u) => u.patientId === own?.id);
  const refused = (queue.data?.failed ?? []).filter((u) => u.patientId === own?.id);

  return (
    <Screen>
      {waiting.length > 0 && (
        <View style={styles.block}>
          <FormMessage kind="warning" text={t("waiting", { n: waiting.length })} />
          <Button variant="link" label={t("sendNow")} onPress={() => void sendWaitingUploads()} />
        </View>
      )}
      {refused.map((f) => (
        <View key={f.id} style={styles.block}>
          <FormMessage
            kind="error"
            text={`${t("refused")} ${f.code ? errorText({ code: f.code }) : ""}`.trim()}
          />
          <Button
            variant="link"
            label={t("dismiss")}
            onPress={() =>
              void dismissFailedUpload(f.id).then(() =>
                queryClient.invalidateQueries({ queryKey: ["uploads"] }),
              )
            }
          />
        </View>
      ))}
      <Title>{t("listTitle")}</Title>
      {own && <Paragraph muted>{t("whoseList", { name: own.full_name })}</Paragraph>}
      {documents.isPending && own ? (
        <LoadingView />
      ) : !documents.data ? (
        <RetryView text={errorText(documents.error)} onRetry={() => void documents.refetch()} />
      ) : documents.data.length === 0 ? (
        <Paragraph>{t("empty")}</Paragraph>
      ) : (
        <View style={[styles.card, { backgroundColor: p.surface, borderColor: p.border }]}>
          {documents.data.map((d, i) => (
            <DocumentRow key={d.id} document={d} first={i === 0} />
          ))}
        </View>
      )}
      <View style={styles.bottom}>
        <Button label={t("open")} onPress={() => router.push("/upload")} />
      </View>
    </Screen>
  );
}

function DocumentRow({ document, first }: { document: DocumentItem; first: boolean }) {
  const t = useTranslations("app.upload");
  const p = usePalette();
  const bad = document.status === "failed" || document.status === "rejected";
  const kind = document.mime_type === "application/pdf" ? t("kindPdf") : t("kindPicture");
  const pages = document.page_count ? t("pages", { n: document.page_count }) : null;
  return (
    <View
      style={[
        styles.row,
        !first && { borderTopColor: p.border, borderTopWidth: StyleSheet.hairlineWidth },
      ]}
      testID={`document-${document.id}`}
    >
      <Icon
        name={STATUS_ICON[document.status] ?? "file-outline"}
        color={bad ? p.danger : p.primary}
      />
      <View style={styles.text}>
        <Text style={[styles.name, { color: p.text }]}>
          {[kind, pages].filter(Boolean).join(" · ")}
        </Text>
        <Text style={[styles.meta, { color: p.textMuted }]}>
          {formatDateTime(document.created_at)}
        </Text>
        <Text
          accessibilityLiveRegion="polite"
          style={[styles.meta, { color: bad ? p.danger : p.text }]}
        >
          {t(`status.${document.status}` as "status.uploaded")}
          {document.error_code === "infected" ? ` — ${t("infected")}` : ""}
        </Text>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  block: { gap: space.xs },
  bottom: { marginTop: space.lg },
  card: { borderRadius: radius.lg, borderWidth: StyleSheet.hairlineWidth, overflow: "hidden" },
  row: {
    flexDirection: "row",
    gap: space.md,
    alignItems: "flex-start",
    paddingHorizontal: space.lg,
    paddingVertical: space.md,
  },
  text: { flex: 1, gap: 2 },
  name: { fontSize: fontSize.body, fontWeight: "600" },
  meta: { fontSize: fontSize.caption },
});
