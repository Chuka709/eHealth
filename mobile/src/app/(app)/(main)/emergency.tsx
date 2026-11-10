import { Stack } from "expo-router";
import { useTranslations } from "use-intl";

import { Screen } from "@/components/screen";
import { LoadingView, RetryView } from "@/components/state-view";
import { EmergencyCardPanel } from "@/features/emergency/card-panel";
import { useEmergencyCard } from "@/features/emergency/use-emergency-card";
import { useOwnProfile } from "@/features/health/record-screens";
import { isNetworkError, useErrorText } from "@/lib/use-error-text";

/**
 * The emergency card (🆘 on Home): the user's own profile. It opens from the saved copy when
 * the phone is offline. A switch at the top shows the whole card, title included, in the
 * other language, for a team abroad.
 */
export default function EmergencyScreen() {
  const e = useTranslations("app.emergency");
  const errorText = useErrorText();
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
    <Screen>
      <EmergencyCardPanel card={card} copy={offline ? "offline" : "live"} top={<CardTitle />} />
    </Screen>
  );
}

// inside the card's provider: the title in the card's language
function CardTitle() {
  const e = useTranslations("app.emergency");
  return <Stack.Screen options={{ title: e("title") }} />;
}
