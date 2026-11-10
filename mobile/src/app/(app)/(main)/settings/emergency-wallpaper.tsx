import { Host, Switch } from "@expo/ui";
import { useRef, useState } from "react";
import { StyleSheet } from "react-native";
import { useTranslations } from "use-intl";

import { Button } from "@/components/button";
import { FormMessage } from "@/components/form-message";
import { Screen } from "@/components/screen";
import { LoadingView, RetryView } from "@/components/state-view";
import { Paragraph } from "@/components/text";
import { useEmergencyCard } from "@/features/emergency/use-emergency-card";
import { shareWallpaper, Wallpaper, type WallpaperView } from "@/features/emergency/wallpaper";
import { useOwnProfile } from "@/features/health/record-screens";
import { type Locale, useLocale } from "@/lib/i18n";

/**
 * The lock-screen wallpaper: a preview of exactly what is saved, the name and date of birth
 * off by default, and the warning before the share sheet. The user saves the image
 * (Save Image) and sets it as wallpaper; the app writes nothing to the gallery itself
 * (user decision 2.7 (a)).
 */
export default function EmergencyWallpaperScreen() {
  const w = useTranslations("app.emergency.wallpaper");
  const e = useTranslations("app.emergency");
  const { patients, own } = useOwnProfile();
  const { card, loading } = useEmergencyCard(own?.id);
  const appLocale = useLocale();
  const [locale, setLocale] = useState<Locale>(appLocale);
  const [name, setName] = useState(false);
  const [birthDate, setBirthDate] = useState(false);
  const [fits, setFits] = useState(true);
  const [busy, setBusy] = useState(false);
  const [problem, setProblem] = useState<"failed" | "unavailable" | null>(null);
  const view = useRef<WallpaperView | null>(null);

  if (patients.isPending || loading) return <LoadingView />;
  if (!card) return <RetryView text={e("noCopy")} onRetry={() => void patients.refetch()} />;

  const share = async () => {
    if (!view.current) return;
    setBusy(true);
    setProblem(null);
    try {
      if ((await shareWallpaper(view.current)) === "unavailable") setProblem("unavailable");
    } catch {
      setProblem("failed");
    } finally {
      setBusy(false);
    }
  };

  return (
    <Screen>
      <FormMessage kind="warning" text={w("warning")} />
      <Paragraph>{w("intro")}</Paragraph>
      <Host matchContents={{ vertical: true }} style={styles.wide}>
        <Switch
          label={w("showName")}
          value={name}
          onValueChange={setName}
          testID="wallpaper-name"
        />
      </Host>
      <Host matchContents={{ vertical: true }} style={styles.wide}>
        <Switch
          label={w("showBirthDate")}
          value={birthDate}
          onValueChange={setBirthDate}
          testID="wallpaper-birth-date"
        />
      </Host>
      <Button
        variant="secondary"
        label={locale === "mn" ? "English" : "Монгол"}
        accessibilityLabel={w(locale === "mn" ? "inEnglish" : "inMongolian")}
        onPress={() => setLocale(locale === "mn" ? "en" : "mn")}
      />
      <Wallpaper
        card={card}
        locale={locale}
        fields={{ name, birthDate }}
        onFit={setFits}
        viewRef={view}
        label={w("previewLabel")}
      />
      {!fits && <FormMessage kind="warning" text={w("tooLong")} quiet />}
      {problem && <FormMessage kind="error" text={w(problem)} />}
      {/* said again where the decision is made */}
      <Paragraph>{w("shareNote")}</Paragraph>
      <Button label={w("share")} busy={busy} onPress={() => void share()} />
      <Paragraph muted>{w("howTo")}</Paragraph>
    </Screen>
  );
}

const styles = StyleSheet.create({ wide: { alignSelf: "stretch" } });
