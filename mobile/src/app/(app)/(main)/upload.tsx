import { fontSize, space } from "@labtrack/shared";
import { useRouter } from "expo-router";
import { useShareIntentContext } from "expo-share-intent";
import { useState } from "react";
import { StyleSheet, View } from "react-native";
import { useTranslations } from "use-intl";

import { Text } from "@/components/app-text";
import { Button } from "@/components/button";
import { FormMessage } from "@/components/form-message";
import { NavGroup, NavRow } from "@/components/nav-row";
import { Screen } from "@/components/screen";
import { Paragraph } from "@/components/text";
import { useRecordProfile } from "@/features/health/record-screens";
import { ProfileSwitcher } from "@/features/records/profile-switcher";
import {
  type Picked,
  pickPdf,
  pickPictures,
  queueFiles,
  scanPages,
} from "@/features/upload/use-uploads";
import { usePalette } from "@/theme/use-palette";

const ACCEPTED = new Set([
  "application/pdf",
  "image/jpeg",
  "image/png",
  "image/heic",
  "image/heif",
  "image/webp",
]);

type Problem = "full" | "pickFailed" | null;

/**
 * Adding a lab result (Phase 3.4; docs/08 "Хариу оруулах"): whose result first (the active
 * profile, changeable here), then a scan, pictures or a PDF. Files wait on the phone until
 * sent - in airplane mode too - and the list of results shows how far each one got.
 */
export default function UploadScreen() {
  const t = useTranslations("app.upload");
  const router = useRouter();
  const { own } = useRecordProfile();
  const p = usePalette();
  const [busy, setBusy] = useState(false);
  const [problem, setProblem] = useState<Problem>(null);
  const share = useShareIntentContext();
  const shared: Picked[] = (share.shareIntent.files ?? [])
    .filter((f) => ACCEPTED.has(f.mimeType))
    .map((f) => ({
      // a plain path may hold spaces or Cyrillic letters: encoded into a file URI (review M4)
      uri:
        f.path.startsWith("file://") || f.path.startsWith("content://")
          ? f.path
          : `file://${encodeURI(f.path)}`,
      mime: f.mimeType,
    }));

  const add = (pick: () => Promise<Picked[]>) => async () => {
    if (!own || busy) return;
    setBusy(true);
    setProblem(null);
    try {
      const files = await pick();
      if (files.length === 0) return; // cancelled
      const outcome = await queueFiles(files, own.id);
      if (outcome === "full") {
        setProblem("full");
        return;
      }
      router.replace("/results");
    } catch {
      setProblem("pickFailed");
    } finally {
      setBusy(false);
    }
  };

  return (
    <Screen>
      <Paragraph>{t("whose")}</Paragraph>
      <ProfileSwitcher />
      {problem && <FormMessage kind="error" text={t(problem)} />}
      {!own && <FormMessage kind="warning" text={t("noProfile")} />}
      {share.hasShareIntent && (
        <View style={styles.shared}>
          {shared.length > 0 ? (
            <>
              <Paragraph>{t("shared", { n: shared.length })}</Paragraph>
              <Button
                label={t("addShared", { name: own?.full_name ?? "" })}
                disabled={!own}
                busy={busy}
                onPress={() =>
                  void add(async () => {
                    share.resetShareIntent();
                    return shared;
                  })()
                }
              />
            </>
          ) : (
            <FormMessage kind="warning" text={t("sharedUnsupported")} />
          )}
          <Button
            variant="link"
            label={t("ignoreShared")}
            onPress={() => share.resetShareIntent()}
          />
        </View>
      )}
      {own && (
        // the profile the files go to, said right above the ways to add them (H29)
        <Text style={[styles.target, { color: p.text }]} testID="upload-target">
          {t("forProfile", { name: own.full_name })}
        </Text>
      )}
      {busy ? (
        <View accessibilityLiveRegion="polite">
          <Paragraph>{t("adding")}</Paragraph>
        </View>
      ) : own ? (
        <NavGroup title={t("how")}>
          <NavRow
            icon="camera-document"
            label={t("scan")}
            hint={t("scanHint")}
            onPress={() => void add(scanPages)()}
            testID="upload-scan"
          />
          <NavRow
            icon="image-multiple-outline"
            label={t("pictures")}
            hint={t("picturesHint")}
            onPress={() => void add(pickPictures)()}
            testID="upload-pictures"
          />
          <NavRow
            icon="file-pdf-box"
            label={t("pdf")}
            hint={t("pdfHint")}
            onPress={() => void add(pickPdf)()}
            testID="upload-pdf"
          />
        </NavGroup>
      ) : null}
      <View style={styles.note}>
        <Paragraph muted>{t("privacy")}</Paragraph>
      </View>
    </Screen>
  );
}

const styles = StyleSheet.create({
  note: { marginTop: space.sm },
  shared: { gap: space.sm },
  target: { fontSize: fontSize.bodyLarge, fontWeight: "600" },
});
