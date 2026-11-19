import { fontSize, radius, space } from "@labtrack/shared";
import { useState } from "react";
import { Platform, StyleSheet, View } from "react-native";
import { useTranslations } from "use-intl";
import { Text } from "@/components/app-text";

import { Button } from "@/components/button";
import { Screen } from "@/components/screen";
import { LoadingView } from "@/components/state-view";
import { Paragraph, Title } from "@/components/text";
import { cardText } from "@/features/emergency/card-text";
import { useEmergencyCard } from "@/features/emergency/use-emergency-card";
import { useOwnProfile } from "@/features/health/record-screens";
import { type Locale, useLocale } from "@/lib/i18n";
import { usePalette } from "@/theme/use-palette";

const IOS_STEPS = ["ios1", "ios2", "ios3", "ios4"] as const;
const ANDROID_STEPS = ["android1", "android2", "android3"] as const;

/**
 * The phone's own emergency information, which no app may write (iPhone Medical ID, Android
 * emergency information): the steps, this phone's system first, and the card's text to copy
 * by hand (selectable), in either language. The app reads and changes nothing there.
 */
export default function MedicalIdScreen() {
  const m = useTranslations("app.emergency.medicalId");
  const p = usePalette();
  const appLocale = useLocale();
  const [locale, setLocale] = useState<Locale>(appLocale);
  const { patients, own } = useOwnProfile();
  const { card, loading } = useEmergencyCard(own?.id);
  if (patients.isPending || loading) return <LoadingView />;

  const ios = (
    <View style={styles.part} key="ios">
      <Title>{m("iosTitle")}</Title>
      {IOS_STEPS.map((k) => (
        <Paragraph key={k}>{m(k)}</Paragraph>
      ))}
    </View>
  );
  const android = (
    <View style={styles.part} key="android">
      <Title>{m("androidTitle")}</Title>
      {ANDROID_STEPS.map((k) => (
        <Paragraph key={k}>{m(k)}</Paragraph>
      ))}
    </View>
  );
  const text = card ? cardText(card, locale) : null;
  return (
    <Screen>
      <Paragraph>{m("intro")}</Paragraph>
      {Platform.OS === "android" ? [android, ios] : [ios, android]}
      <Title>{m("copyTitle")}</Title>
      {text ? (
        <>
          <Button
            variant="secondary"
            label={locale === "mn" ? "English" : "Монгол"}
            accessibilityLabel={m(locale === "mn" ? "inEnglish" : "inMongolian")}
            onPress={() => setLocale(locale === "mn" ? "en" : "mn")}
          />
          <View style={[styles.copy, { borderColor: p.border, backgroundColor: p.surface }]}>
            <Text selectable style={[styles.copyText, { color: p.text }]} testID="medical-id-text">
              {[...text.front, ...text.back]
                .map((s) => [s.heading, ...s.lines].filter(Boolean).join("\n"))
                .join("\n\n")}
            </Text>
          </View>
        </>
      ) : (
        <Paragraph>{m("noCard")}</Paragraph>
      )}
      <Paragraph muted>{m("keepCurrent")}</Paragraph>
    </Screen>
  );
}

const styles = StyleSheet.create({
  part: { gap: space.sm },
  copy: { borderWidth: StyleSheet.hairlineWidth * 2, borderRadius: radius.md, padding: space.md },
  copyText: { fontSize: fontSize.body, lineHeight: fontSize.body * 1.4 },
});
