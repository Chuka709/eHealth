import { fontSize, radius, space } from "@labtrack/shared";
import { Alert, StyleSheet, View } from "react-native";
import { useTranslations } from "use-intl";
import { Text } from "@/components/app-text";

import { Button } from "@/components/button";
import { FormMessage } from "@/components/form-message";
import { Screen } from "@/components/screen";
import { LoadingView, RetryView } from "@/components/state-view";
import { Paragraph } from "@/components/text";
import { useMyInvitations, useRespond } from "@/features/caregivers/use-caregivers";
import { useMyShareInvitations, useRespondShare } from "@/features/shares/use-shares";
import { formatDate } from "@/lib/dates";
import { useErrorText } from "@/lib/use-error-text";
import { usePalette } from "@/theme/use-palette";

/**
 * Invitations to be someone's caregiver, or to see a profile as a doctor or a viewer (7.1):
 * who asks (the profile's name only after accepting - Q45). Accepting says what it means
 * first; "no" is always possible.
 */
export default function InvitationsScreen() {
  const t = useTranslations("app.caregivers.invitations");
  const tc = useTranslations("app.common");
  const p = usePalette();
  const errorText = useErrorText();
  const list = useMyInvitations();
  const respond = useRespond();
  const ts = useTranslations("app.shares.invitations");
  const tl = useTranslations("app.shares");
  const shares = useMyShareInvitations();
  const respondShare = useRespondShare();

  if (list.isPending && shares.isPending) return <LoadingView />;
  if (!list.data && !shares.data) {
    return (
      <RetryView
        text={errorText(list.error ?? shares.error)}
        onRetry={() => {
          void list.refetch();
          void shares.refetch();
        }}
      />
    );
  }
  // caregiver and doctor/viewer invitations (7.1): one list failing never hides the other
  const careList = list.data ?? [];
  const shareList = shares.data ?? [];
  const acceptShare = (id: string, who: string, level: "doctor" | "viewer") =>
    Alert.alert(
      ts("acceptTitle", { name: who }),
      ts(`acceptBody.${level}`),
      [
        { text: tc("cancel"), style: "cancel" },
        {
          text: t("accept"),
          onPress: () => respondShare.mutate({ invitation_id: id, accept: true }),
        },
      ],
      { cancelable: true },
    );
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
      {list.isError && <FormMessage kind="error" text={errorText(list.error)} />}
      {shares.isError && <FormMessage kind="error" text={errorText(shares.error)} />}
      {respond.isError && <FormMessage kind="error" text={errorText(respond.error)} />}
      {respondShare.isError && <FormMessage kind="error" text={errorText(respondShare.error)} />}
      {careList.length === 0 && shareList.length === 0 && !list.isPending && !shares.isPending && (
        <Paragraph muted>{t("none")}</Paragraph>
      )}
      {shareList.map((i) => (
        <View
          key={i.id}
          style={[styles.card, { backgroundColor: p.surface, borderColor: p.border }]}
        >
          <Text style={[styles.name, { color: p.text }]}>
            {ts("from", { name: i.inviter_name, level: tl(`level.${i.level}`) })}
          </Text>
          <Paragraph>
            {i.access_days ? tl("duration.days", { n: i.access_days }) : tl("duration.open")}
          </Paragraph>
          <Paragraph muted>{t("expires", { date: formatDate(i.expires_at) })}</Paragraph>
          <Button
            label={t("accept")}
            disabled={respondShare.isPending}
            accessibilityLabel={ts("acceptLabel", { name: i.inviter_name })}
            onPress={() => acceptShare(i.id, i.inviter_name, i.level)}
          />
          <Button
            variant="secondary"
            label={t("decline")}
            accessibilityLabel={t("declineLabel", { name: i.inviter_name })}
            disabled={respondShare.isPending}
            onPress={() => respondShare.mutate({ invitation_id: i.id, accept: false })}
          />
        </View>
      ))}
      {careList.map((i) => (
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
    </Screen>
  );
}

const styles = StyleSheet.create({
  card: { borderWidth: 1, borderRadius: radius.md, padding: space.md, gap: space.sm },
  name: { fontSize: fontSize.body, fontWeight: "700" },
});
