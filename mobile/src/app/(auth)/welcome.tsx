import { fontSize, radius, space } from "@labtrack/shared";
import { useRouter } from "expo-router";
import { StyleSheet, View } from "react-native";
import { useTranslations } from "use-intl";

import { Text } from "@/components/app-text";
import { Button } from "@/components/button";
import { Icon } from "@/components/icon";
import { Screen } from "@/components/screen";
import { Paragraph } from "@/components/text";
import { usePalette } from "@/theme/use-palette";

/** First screen without an account on the phone: a calm mark, what to do, two actions. */
export default function WelcomeScreen() {
  const t = useTranslations("app.welcome");
  const router = useRouter();
  const p = usePalette();
  return (
    <Screen safeTop>
      <View style={styles.hero}>
        <View style={[styles.mark, { backgroundColor: p.primarySoft }]}>
          <Icon name="heart-pulse" color={p.primary} size={48} />
        </View>
        <Text accessibilityRole="header" style={[styles.title, { color: p.text }]}>
          {t("title")}
        </Text>
        <Paragraph muted>{t("body")}</Paragraph>
      </View>
      <View style={styles.actions}>
        <Button label={t("activate")} onPress={() => router.push("/activate")} />
        <Button variant="secondary" label={t("login")} onPress={() => router.push("/login")} />
      </View>
    </Screen>
  );
}

const styles = StyleSheet.create({
  hero: { gap: space.lg, paddingTop: space.xxl * 2, paddingBottom: space.xl },
  mark: {
    width: 88,
    height: 88,
    borderRadius: radius.pill,
    alignItems: "center",
    justifyContent: "center",
  },
  title: { fontSize: fontSize.display, fontWeight: "700", lineHeight: fontSize.display * 1.2 },
  actions: { gap: space.md },
});
