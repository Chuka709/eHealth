import { Host, Switch } from "@expo/ui";
import { fontSize, radius, space } from "@labtrack/shared";
import bundledVersions from "@labtrack/shared/consent-versions.json";
import { Alert, StyleSheet, Text, View } from "react-native";
import { useTranslations } from "use-intl";

import { Button } from "@/components/button";
import { FormMessage } from "@/components/form-message";
import { Screen } from "@/components/screen";
import { LoadingView, RetryView } from "@/components/state-view";
import { Paragraph } from "@/components/text";
import {
  AI_KINDS,
  type ConsentKind,
  type ConsentState,
  REQUIRED_KINDS,
  useConsents,
  useGiveConsents,
} from "@/features/consents/use-consents";
import { formatDateTime } from "@/lib/dates";
import { ApiError, useErrorText } from "@/lib/use-error-text";
import { usePalette } from "@/theme/use-palette";

/**
 * Consents as given (docs/04 §5): withdrawing is never harder than giving. A required one
 * withdrawn sends the user to the consents screen (guard in (app)/_layout); the AI pair is
 * switched on and off together.
 */
export default function ConsentSettingsScreen() {
  const t = useTranslations("app");
  const errorText = useErrorText();
  const consents = useConsents();
  const give = useGiveConsents();
  if (consents.isPending) return <LoadingView />;
  if (!consents.data) {
    return <RetryView text={errorText(consents.error)} onRetry={() => void consents.refetch()} />;
  }
  const byKind = new Map(consents.data.map((s) => [s.kind, s]));
  // On while either part is still given: off withdraws both (allowed one by one too).
  const aiOn = AI_KINDS.some((kind) => byKind.get(kind)?.granted === true);
  const item = (kind: ConsentKind, granted: boolean) => ({
    kind,
    granted,
    version: bundledVersions[kind],
  });
  const outdated = give.error instanceof ApiError && give.error.code === "consent.version_outdated";

  const withdraw = (kind: (typeof REQUIRED_KINDS)[number]) =>
    Alert.alert(t("consentSettings.withdrawTitle"), t("consentSettings.withdrawBody"), [
      { text: t("common.cancel"), style: "cancel" },
      {
        text: t("consentSettings.withdrawConfirm"),
        style: "destructive",
        onPress: () => give.mutate([item(kind, false)]),
      },
    ]);

  return (
    <Screen>
      {REQUIRED_KINDS.map((kind) => (
        <ConsentRow key={kind} state={byKind.get(kind)} title={t(`consent.${kind}.title`)}>
          {byKind.get(kind)?.granted && (
            <Button
              variant="danger"
              label={t("consentSettings.withdraw")}
              accessibilityLabel={t("consentSettings.withdrawLabel", {
                consent: t(`consent.${kind}.title`),
              })}
              disabled={give.isPending}
              onPress={() => withdraw(kind)}
            />
          )}
        </ConsentRow>
      ))}
      <ConsentRow state={byKind.get("ai_processing")} title={t("consent.ai.title")}>
        <Paragraph muted>{t("consent.ai.summary")}</Paragraph>
        <Host matchContents={{ vertical: true }} style={styles.wide}>
          <Switch
            label={t("consent.ai.title")}
            value={aiOn}
            disabled={give.isPending}
            onValueChange={(on) => give.mutate(AI_KINDS.map((kind) => item(kind, on)))}
            testID="consent-settings-ai"
          />
        </Host>
      </ConsentRow>
      {give.isError && (
        <FormMessage
          kind="error"
          text={outdated ? t("consent.appOutdated") : errorText(give.error)}
        />
      )}
    </Screen>
  );
}

function ConsentRow({
  state,
  title,
  children,
}: {
  state: ConsentState | undefined;
  title: string;
  children: React.ReactNode;
}) {
  const t = useTranslations("app.consentSettings");
  const p = usePalette();
  const status =
    state?.granted && state.at ? t("given", { date: formatDateTime(state.at) }) : t("notGiven");
  return (
    <View style={[styles.row, { backgroundColor: p.surface, borderColor: p.border }]}>
      <View accessible accessibilityLabel={`${title}. ${status}`}>
        <Text style={[styles.title, { color: p.text }]}>{title}</Text>
        <Paragraph muted>{status}</Paragraph>
      </View>
      {children}
    </View>
  );
}

const styles = StyleSheet.create({
  row: {
    gap: space.sm,
    padding: space.md,
    borderRadius: radius.md,
    borderWidth: StyleSheet.hairlineWidth * 2,
  },
  title: { fontSize: fontSize.body, fontWeight: "600" },
  wide: { width: "100%" },
});
