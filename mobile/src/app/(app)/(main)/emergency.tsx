import { Stack } from "expo-router";
import { useState } from "react";
import { useTranslations } from "use-intl";

import { Button } from "@/components/button";
import { Screen } from "@/components/screen";
import { LoadingView, RetryView } from "@/components/state-view";
import { EmergencyCardView } from "@/features/emergency/emergency-card-view";
import { useEmergencyCard } from "@/features/emergency/use-emergency-card";
import { useOwnProfile } from "@/features/health/record-screens";
import { I18nProvider, type Locale, useLocale } from "@/lib/i18n";
import { isNetworkError, useErrorText } from "@/lib/use-error-text";

/**
 * The emergency card (🆘 on Home): the user's own profile. It opens from the saved copy when
 * the phone is offline. A link at the top switches the whole card, title included, to the
 * other language, for a team abroad.
 */
export default function EmergencyScreen() {
  const e = useTranslations("app.emergency");
  const errorText = useErrorText();
  const appLocale = useLocale();
  const [locale, setLocale] = useState<Locale | null>(null);
  const shown = locale ?? appLocale;
  const { patients, own } = useOwnProfile();
  const { card, offline, loading, error, refetch } = useEmergencyCard(own?.id);

  if (patients.isPending || loading) return <LoadingView />;
  if (!card) {
    const text = patients.error
      ? errorText(patients.error)
      : !own
        ? e("noProfile")
        : error && !isNetworkError(error)
          ? errorText(error)
          : e("noCopy"); // offline, nothing saved yet
    return <RetryView text={text} onRetry={refetch} />;
  }
  return (
    <I18nProvider locale={shown}>
      <CardTitle />
      <Screen>
        <SwitchLanguage onPress={() => setLocale(shown === "mn" ? "en" : "mn")} />
        <EmergencyCardView card={card} offline={offline} />
      </Screen>
    </I18nProvider>
  );
}

// inside the card's provider: the title in the card's language
function CardTitle() {
  const e = useTranslations("app.emergency");
  return <Stack.Screen options={{ title: e("title") }} />;
}

// the other language, named in that language: the first thing a foreign team can read
function SwitchLanguage({ onPress }: { onPress: () => void }) {
  const e = useTranslations("app.emergency");
  return (
    <Button
      variant="secondary"
      label={e("switchTo")}
      accessibilityLabel={e("switchToLabel")}
      onPress={onPress}
    />
  );
}
