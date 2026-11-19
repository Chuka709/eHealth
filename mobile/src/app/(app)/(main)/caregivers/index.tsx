import { fontSize, radius, space } from "@labtrack/shared";
import { useRouter } from "expo-router";
import { useState } from "react";
import { Alert, StyleSheet, View } from "react-native";
import { useTranslations } from "use-intl";
import { Text } from "@/components/app-text";

import { Button } from "@/components/button";
import { FormMessage } from "@/components/form-message";
import { Screen } from "@/components/screen";
import { LoadingView, RetryView } from "@/components/state-view";
import { Paragraph, Title } from "@/components/text";
import { TextField } from "@/components/text-field";
import {
  useCancelInvitation,
  useCaregivers,
  useEndAccess,
  useInvite,
  usePause,
} from "@/features/caregivers/use-caregivers";
import { useRecordProfile } from "@/features/health/record-screens";
import { usePinnedProfile } from "@/features/records/active-profile";
import { ProfileBanner } from "@/features/records/profile-banner";
import { ProfileChanged } from "@/features/records/profile-changed";
import { formatDate } from "@/lib/dates";
import { ApiError, useErrorText } from "@/lib/use-error-text";
import { usePalette } from "@/theme/use-palette";

const USERNAME = /^[a-z0-9._]{3,32}$/;

/**
 * The owner's caregivers (2.8d API): who has access, their alerts (pause / resume), ending
 * access, open invitations, and inviting by username - after checking the username, since a
 * mistyped one sends the owner's name to someone else (Q45).
 */
export default function CaregiversScreen() {
  const t = useTranslations("app.caregivers");
  const tc = useTranslations("app.common");
  const router = useRouter();
  const p = usePalette();
  const errorText = useErrorText();
  const { patients, own: active } = useRecordProfile();
  // pinned: an invitation never goes to a profile other than the one this screen opened on
  const { pinned: own, changed } = usePinnedProfile(active);
  const isOwner = own?.access_level === "owner";
  const list = useCaregivers(own?.id, { enabled: isOwner && !own?.is_minor });
  const invite = useInvite(own?.id ?? "");
  const cancel = useCancelInvitation(own?.id ?? "");
  const end = useEndAccess(own?.id ?? "");
  const pause = usePause(own?.id ?? "");
  const [username, setUsername] = useState("");
  const [sent, setSent] = useState(false);

  if (changed) return <ProfileChanged />;
  if (patients.isPending) return <LoadingView />;
  if (!own) {
    return <RetryView text={errorText(patients.error)} onRetry={() => void patients.refetch()} />;
  }
  if (!isOwner) {
    return (
      <Screen>
        <Paragraph>{t("ownerOnly")}</Paragraph>
      </Screen>
    );
  }
  if (own.is_minor) {
    return (
      <Screen>
        <ProfileBanner />
        <Paragraph>{t("minor")}</Paragraph>
      </Screen>
    );
  }
  if (list.isPending) return <LoadingView />;
  if (!list.data) {
    return <RetryView text={errorText(list.error)} onRetry={() => void list.refetch()} />;
  }

  const name = username.trim().toLowerCase();
  const valid = USERNAME.test(name);
  const needsConsent =
    invite.error instanceof ApiError && invite.error.code === "caregiver.consent_required";
  const send = () =>
    Alert.alert(
      t("invite.checkTitle"),
      t("invite.checkBody", { username: name }),
      [
        { text: tc("cancel"), style: "cancel" },
        {
          text: t("invite.send"),
          onPress: () => {
            setSent(false);
            invite.mutate(name, {
              onSuccess: () => {
                setSent(true);
                setUsername("");
              },
            });
          },
        },
      ],
      { cancelable: true },
    );
  const confirmEnd = (userId: string, who: string) =>
    Alert.alert(
      t("end.title", { name: who }),
      t("end.body"),
      [
        { text: tc("cancel"), style: "cancel" },
        { text: t("end.confirm"), style: "destructive", onPress: () => end.mutate(userId) },
      ],
      { cancelable: true },
    );

  return (
    <Screen>
      <ProfileBanner />
      <Paragraph>{t("intro")}</Paragraph>

      <Title>{t("listTitle")}</Title>
      {list.data.caregivers.length === 0 && <Paragraph muted>{t("none")}</Paragraph>}
      {list.data.caregivers.map((c) => (
        <View
          key={c.user_id}
          style={[styles.card, { backgroundColor: p.surface, borderColor: p.border }]}
        >
          <Text style={[styles.name, { color: p.text }]}>{c.display_name}</Text>
          {c.since && <Paragraph muted>{t("since", { date: formatDate(c.since) })}</Paragraph>}
          <Paragraph>
            {c.owner_paused
              ? t("alerts.paused")
              : c.missed_dose_after_min === null
                ? t("alerts.off")
                : t("alerts.on", { minutes: c.missed_dose_after_min })}
          </Paragraph>
          <Button
            variant="secondary"
            label={c.owner_paused ? t("resume") : t("pause")}
            accessibilityLabel={
              c.owner_paused
                ? t("resumeLabel", { name: c.display_name })
                : t("pauseLabel", { name: c.display_name })
            }
            disabled={pause.isPending}
            onPress={() =>
              c.owner_paused
                ? pause.mutate({ userId: c.user_id, paused: false })
                : Alert.alert(
                    t("pauseTitle", { name: c.display_name }),
                    t("pauseBody"),
                    [
                      { text: tc("cancel"), style: "cancel" },
                      {
                        text: t("pause"),
                        onPress: () => pause.mutate({ userId: c.user_id, paused: true }),
                      },
                    ],
                    { cancelable: true },
                  )
            }
          />
          <Button
            variant="danger"
            label={t("end.button")}
            accessibilityLabel={t("end.title", { name: c.display_name })}
            disabled={end.isPending}
            onPress={() => confirmEnd(c.user_id, c.display_name)}
          />
        </View>
      ))}

      {list.data.invitations.length > 0 && <Title>{t("pendingTitle")}</Title>}
      {list.data.invitations.map((i) => (
        <View
          key={i.id}
          style={[styles.card, { backgroundColor: p.surface, borderColor: p.border }]}
        >
          <Text style={[styles.name, { color: p.text }]}>{i.username}</Text>
          <Paragraph muted>{t("expires", { date: formatDate(i.expires_at) })}</Paragraph>
          <Button
            variant="secondary"
            label={t("cancelInvite")}
            accessibilityLabel={t("cancelInviteLabel", { username: i.username })}
            disabled={cancel.isPending}
            onPress={() => cancel.mutate(i.id)}
          />
        </View>
      ))}

      <Title>{t("invite.title")}</Title>
      <Paragraph muted>{t("invite.hint")}</Paragraph>
      <TextField
        label={t("invite.username")}
        value={username}
        onChangeText={(v) => {
          setUsername(v);
          setSent(false);
        }}
        autoCapitalize="none"
        autoCorrect={false}
        error={username.length > 0 && !valid ? t("invite.invalid") : undefined}
        testID="caregiver-username"
      />
      <Button
        label={t("invite.button")}
        disabled={!valid || invite.isPending}
        busy={invite.isPending}
        onPress={send}
      />
      {sent && <FormMessage kind="success" text={t("invite.sent")} />}
      {needsConsent && (
        <>
          <FormMessage kind="warning" text={t("invite.needsConsent")} />
          <Button
            variant="link"
            label={t("invite.openConsents")}
            onPress={() => router.push("/settings/consents")}
          />
        </>
      )}
      {invite.isError && !needsConsent && (
        <FormMessage kind="error" text={errorText(invite.error)} />
      )}
      {(cancel.isError || end.isError || pause.isError) && (
        <FormMessage kind="error" text={errorText(cancel.error ?? end.error ?? pause.error)} />
      )}
    </Screen>
  );
}

const styles = StyleSheet.create({
  card: { borderWidth: 1, borderRadius: radius.md, padding: space.md, gap: space.sm },
  name: { fontSize: fontSize.body, fontWeight: "700" },
});
