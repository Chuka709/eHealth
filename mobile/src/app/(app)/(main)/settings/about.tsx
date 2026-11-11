import { space } from "@labtrack/shared";
import Constants from "expo-constants";
import * as Linking from "expo-linking";
import { useState } from "react";
import { StyleSheet, View } from "react-native";
import { useTranslations } from "use-intl";

import { Button } from "@/components/button";
import { FormMessage } from "@/components/form-message";
import { Screen } from "@/components/screen";
import { Paragraph, Title } from "@/components/text";
import { CallSupportButton } from "@/features/auth/support-contact";
import { privacyPolicyUrl, supportPhone } from "@/lib/support";

/**
 * Settings -> About (Phase 2.11d; docs/09 "Зориулалт", docs/08 "Дэлгүүрт гаргах"): what the app
 * is for and what it never does, the privacy policy and the support line. Plain text only.
 */
export default function AboutScreen() {
  const t = useTranslations("app.about");
  const [failed, setFailed] = useState(false);
  const version = Constants.expoConfig?.version ?? "";
  const privacy = privacyPolicyUrl;

  return (
    <Screen>
      <View style={styles.section}>
        <Title>{t("purposeTitle")}</Title>
        <Paragraph>{t("purpose")}</Paragraph>
      </View>
      <View style={styles.section}>
        <Title>{t("notTitle")}</Title>
        <Paragraph>{t("not")}</Paragraph>
        <Paragraph>{t("reliability")}</Paragraph>
        <Paragraph>{t("emergency")}</Paragraph>
        <Button
          variant="secondary"
          label={t("call103")}
          onPress={() => void Linking.openURL("tel:103").catch(() => undefined)}
        />
      </View>
      {privacy && (
        <View style={styles.section}>
          <Title>{t("privacyTitle")}</Title>
          <Button
            variant="link"
            label={t("privacy")}
            onPress={() => {
              setFailed(false);
              void Linking.openURL(privacy).catch(() => setFailed(true));
            }}
          />
          {failed && <FormMessage kind="error" text={t("privacyFailed")} />}
        </View>
      )}
      {supportPhone && (
        <View style={styles.section}>
          <Title>{t("support")}</Title>
          <CallSupportButton variant="secondary" />
        </View>
      )}
      {version !== "" && <Paragraph muted>{t("version", { version })}</Paragraph>}
    </Screen>
  );
}

const styles = StyleSheet.create({
  section: { gap: space.sm, marginBottom: space.lg },
});
