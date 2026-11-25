import { fontSize, radius, space } from "@labtrack/shared";
import { Stack, useRouter } from "expo-router";
import { Pressable, StyleSheet, View } from "react-native";
import { useTranslations } from "use-intl";

import { Text } from "@/components/app-text";
import { Button } from "@/components/button";
import { FormMessage } from "@/components/form-message";
import { HeaderAdd } from "@/components/header-add";
import { Icon, type IconName } from "@/components/icon";
import { Screen } from "@/components/screen";
import { LoadingView, RetryView } from "@/components/state-view";
import { Paragraph } from "@/components/text";
import { useRecordProfile } from "@/features/health/record-screens";
import { useTypedReports } from "@/features/review/use-review";
import { dismissFailedUpload } from "@/features/upload/upload-queue";
import { failReason } from "@/features/upload/use-reports";
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
  const typed = useTypedReports(own?.id);
  // a typed-in report has no file: "rejected" is the person's own choice, not a refused file
  const typedStatus = (status: string) =>
    status === "rejected" ? t("review.rejected") : t(`status.${status}` as "status.uploaded");
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
      {/* the header already says "Шинжилгээний хариунууд" (UX audit #9) */}
      <Stack.Screen
        options={{
          headerRight: () => (
            <HeaderAdd
              label={t("open")}
              onPress={() => router.push("/upload")}
              testID="results-add-header"
            />
          ),
        }}
      />
      {own && <Paragraph muted>{t("whoseList", { name: own.full_name })}</Paragraph>}
      {documents.isPending && own && documents.fetchStatus === "paused" ? (
        <Paragraph muted>{t("listOffline")}</Paragraph>
      ) : documents.isPending && own ? (
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
      {(typed.data ?? []).length > 0 && (
        <View style={styles.block}>
          <Text accessibilityRole="header" style={[styles.name, { color: p.text }]}>
            {t("review.typed")}
          </Text>
          <View style={[styles.card, { backgroundColor: p.surface, borderColor: p.border }]}>
            {(typed.data ?? []).map((r, i) => (
              <Pressable
                key={r.id}
                onPress={() => router.push({ pathname: "/results/[id]", params: { id: r.id } })}
                accessibilityRole="button"
                accessibilityLabel={[
                  r.lab_name ?? t("review.untitled"),
                  r.collected_at ? formatDateTime(r.collected_at) : null,
                  typedStatus(r.status),
                ]
                  .filter(Boolean)
                  .join(". ")}
                style={({ pressed }) => [
                  styles.row,
                  i > 0 && { borderTopColor: p.border, borderTopWidth: StyleSheet.hairlineWidth },
                  { opacity: pressed ? 0.85 : 1 },
                ]}
                testID={`typed-${r.id}`}
              >
                <Icon name={STATUS_ICON[r.status] ?? "file-outline"} color={p.primary} />
                <View style={styles.text}>
                  <Text style={[styles.name, { color: p.text }]}>
                    {r.lab_name ?? t("review.untitled")}
                  </Text>
                  <Text style={[styles.meta, { color: p.textMuted }]}>
                    {r.collected_at ? formatDateTime(r.collected_at) : t("review.dateUnknown")}
                  </Text>
                  <Text style={[styles.meta, { color: p.text }]}>{typedStatus(r.status)}</Text>
                </View>
                <Icon name="chevron-right" color={p.textMuted} />
              </Pressable>
            ))}
          </View>
        </View>
      )}
      <View style={styles.bottom}>
        <Button label={t("open")} onPress={() => router.push("/upload")} />
        {/* a paper result: typed in by hand (Phase 5.4) */}
        <Button
          label={t("review.typeIn")}
          variant="secondary"
          onPress={() => router.push("/results/new")}
        />
      </View>
    </Screen>
  );
}

function DocumentRow({ document, first }: { document: DocumentItem; first: boolean }) {
  const t = useTranslations("app.upload");
  const router = useRouter();
  const p = usePalette();
  const bad = document.status === "failed" || document.status === "rejected";
  const kind = document.mime_type === "application/pdf" ? t("kindPdf") : t("kindPicture");
  const pages = document.page_count ? t("pages", { n: document.page_count }) : null;
  const reason = bad ? failReason(document.error_code) : null;
  // a reading to look at: the draft (needs_review) or the confirmed report
  const opens = document.status === "needs_review" || document.status === "confirmed";
  const status = t(`status.${document.status}` as "status.uploaded");
  const why = reason ? t(`failReason.${reason}`) : null;
  return (
    <Pressable
      disabled={!opens}
      onPress={() => router.push({ pathname: "/results/[id]", params: { id: document.id } })}
      accessibilityRole={opens ? "button" : undefined}
      accessibilityLabel={[kind, pages, formatDateTime(document.created_at), status, why]
        .filter(Boolean)
        .join(". ")}
      accessibilityHint={opens ? t("review.open") : undefined}
      // the row is one element for a screen reader: its status changes are announced here
      accessibilityLiveRegion="polite"
      style={({ pressed }) => [
        styles.row,
        !first && { borderTopColor: p.border, borderTopWidth: StyleSheet.hairlineWidth },
        { opacity: pressed ? 0.85 : 1 },
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
        <Text style={[styles.meta, { color: bad ? p.danger : p.text }]}>{status}</Text>
        {why && <Text style={[styles.meta, { color: p.textMuted }]}>{why}</Text>}
        {/* not read automatically (a scan or photo - Q50): the person types the values in */}
        {reason === "not_read" && document.status === "failed" && (
          <Button
            label={t("review.typeIn")}
            variant="link"
            compact
            onPress={() =>
              router.push({ pathname: "/results/new", params: { document: document.id } })
            }
          />
        )}
        {opens && (
          <Text style={[styles.meta, styles.link, { color: p.primary }]}>{t("review.open")}</Text>
        )}
      </View>
      {opens && <Icon name="chevron-right" color={p.textMuted} />}
    </Pressable>
  );
}

const styles = StyleSheet.create({
  block: { gap: space.xs },
  bottom: { marginTop: space.lg, gap: space.sm },
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
  link: { fontWeight: "600" },
});
