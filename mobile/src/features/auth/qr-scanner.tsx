import { radius, space } from "@labtrack/shared";
import { CameraView, useCameraPermissions } from "expo-camera";
import * as Linking from "expo-linking";
import { useRef, useState } from "react";
import { StyleSheet, View } from "react-native";
import { useTranslations } from "use-intl";

import { Button } from "@/components/button";
import { FormMessage } from "@/components/form-message";
import { Spinner } from "@/components/spinner";
import { Paragraph } from "@/components/text";
import { usePalette } from "@/theme/use-palette";
import { parseActivationLink } from "./activation-link";

// The camera reports the same code many times a second; do not re-announce a wrong one.
const INVALID_COOLDOWN_MS = 2000;

/** Camera QR scanner that accepts only LabTrack activation links. */
export function ActivationQrScanner({ onToken }: { onToken: (token: string) => void }) {
  const t = useTranslations("app");
  const p = usePalette();
  const [permission, requestPermission] = useCameraPermissions();
  const [invalid, setInvalid] = useState(false);
  const done = useRef(false);
  const lastInvalid = useRef(0);

  if (!permission) {
    return (
      <View accessible accessibilityLabel={t("common.loading")}>
        <Spinner />
      </View>
    );
  }

  if (!permission.granted) {
    return (
      <View style={styles.gap}>
        <Paragraph>{t("activate.cameraNeeded")}</Paragraph>
        {permission.canAskAgain ? (
          <Button label={t("activate.cameraAllow")} onPress={() => void requestPermission()} />
        ) : (
          <Button
            label={t("activate.cameraSettings")}
            onPress={() => void Linking.openSettings()}
          />
        )}
        <Paragraph muted>{t("activate.noCamera")}</Paragraph>
      </View>
    );
  }

  return (
    <View style={styles.gap}>
      <Paragraph>{t("activate.scanHint")}</Paragraph>
      <View
        accessible
        accessibilityLabel={t("activate.cameraLabel")}
        style={[styles.frame, { borderColor: p.border }]}
      >
        <CameraView
          style={StyleSheet.absoluteFill}
          facing="back"
          barcodeScannerSettings={{ barcodeTypes: ["qr"] }}
          onBarcodeScanned={({ data }) => {
            if (done.current) return;
            const token = parseActivationLink(data);
            if (token) {
              done.current = true;
              onToken(token);
              return;
            }
            const now = Date.now();
            if (now - lastInvalid.current < INVALID_COOLDOWN_MS) return;
            lastInvalid.current = now;
            setInvalid(true);
          }}
        />
      </View>
      {invalid && <FormMessage kind="error" text={t("activate.scanInvalid")} />}
      <Paragraph muted>{t("activate.noCamera")}</Paragraph>
    </View>
  );
}

const styles = StyleSheet.create({
  gap: { gap: space.lg },
  frame: {
    width: "100%",
    aspectRatio: 1,
    borderRadius: radius.lg,
    borderWidth: StyleSheet.hairlineWidth * 2,
    overflow: "hidden",
  },
});
