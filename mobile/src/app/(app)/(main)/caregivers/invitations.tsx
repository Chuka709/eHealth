import { fontSize, radius, space } from "@labtrack/shared";
import { Alert, StyleSheet, Text, View } from "react-native";
import { useTranslations } from "use-intl";

import { Button } from "@/components/button";
import { FormMessage } from "@/components/form-message";
import { Screen } from "@/components/screen";
import { LoadingView, RetryView } from "@/components/state-view";
import { Paragraph } from "@/components/text";
import { useMyInvitations, useRespond } from "@/features/caregivers/use-caregivers";
import { formatDate } from "@/lib/dates";
import { useErrorText } from "@/lib/use-error-text";
import { usePalette } from "@/theme/use-palette";

/**
 * Invitations to be someone's caregiver: who asks (the profile's name only after accepting -
 * Q45). Accepting says what it means first; "no" is always possible.
 */
export default function InvitationsScreen() {
  const t = useTranslations("app.caregivers.invitations");
  const tc = useTranslations("app.common");
  const p = usePalette();
  const errorText = useErrorText();
  const list = useMyInvitations();
  const respond = useRespond();

  if (list.isPending) return <LoadingView />;
  if (!list.data) {
    return <RetryView text={errorText(list.error)} onRetry={() => void list.refetch()} />;
  }
  const accept = (id: string, who: string) =>
    Alert.alert(
      t("acceptTitle", { name: who }),
      t("acceptBody"),
      [
        { text: tc("cancel"), style: "cancel" },
        {
          text: t("accept"),
          onPress: () => respond.mutate({ invitation_id: id, accept: true }),
        },
      ],
      { cancelable: true },
    );
  return (
    <Screen>
      {list.data.length === 0 && <Paragraph muted>{t("none")}</Paragraph>}
      {list.data.map((i) => (
        <View
          key={i.id}
          style={[styles.card, { backgroundColor: p.surface, borderColor: p.border }]}
        >
          <Text style={[styles.name, { color: p.text }]}>
            {t("from", { name: i.inviter_name })}
          </Text>
          <Paragraph muted>{t("expires", { date: formatDate(i.expires_at) })}</Paragraph>
          <Button
            label={t("accept")}
            disabled={respond.isPending}
            accessibilityLabel={t("acceptTitle", { name: i.inviter_name })}
            onPress={() => accept(i.id, i.inviter_name)}
          />
          <Button
            variant="secondary"
            label={t("decline")}
            accessibilityLabel={t("declineLabel", { name: i.inviter_name })}
            disabled={respond.isPending}
            onPress={() => respond.mutate({ invitation_id: i.id, accept: false })}
          />
        </View>
      ))}
      {respond.isError && <FormMessage kind="error" text={errorText(respond.error)} />}
    </Screen>
  );
}

const styles = StyleSheet.create({
  card: { borderWidth: 1, borderRadius: radius.md, padding: space.md, gap: space.sm },
  name: { fontSize: fontSize.body, fontWeight: "700" },
});
