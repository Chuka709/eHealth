import { fontSize, radius, space } from "@labtrack/shared";
import { useState } from "react";
import { Alert, StyleSheet, View } from "react-native";
import { useTranslations } from "use-intl";
import { Text } from "@/components/app-text";

import { Button } from "@/components/button";
import { FormMessage } from "@/components/form-message";
import { Screen } from "@/components/screen";
import { Segmented } from "@/components/segmented";
import { InlineLoading, LoadingView, RetryView } from "@/components/state-view";
import { Paragraph, Title } from "@/components/text";
import { TextField } from "@/components/text-field";
import { useRecordProfile } from "@/features/health/record-screens";
import { usePinnedProfile } from "@/features/records/active-profile";
import { ProfileBanner } from "@/features/records/profile-banner";
import { ProfileChanged } from "@/features/records/profile-changed";
import {
  type ShareDays,
  type ShareLevel,
  useCancelShareInvitation,
  useEndShare,
  useInviteShare,
  useShares,
  useShareViews,
} from "@/features/shares/use-shares";
import { formatDate, formatDateTime } from "@/lib/dates";
import { useErrorText } from "@/lib/use-error-text";
import { usePalette } from "@/theme/use-palette";

const USERNAME = /^[a-z0-9._]{3,32}$/;
const LEVELS = ["doctor", "viewer"] as const;
const DURATIONS = ["1", "7", "30", "open"] as const;
type Duration = (typeof DURATIONS)[number];
const toDays = (d: Duration): ShareDays => (d === "open" ? null : (Number(d) as 1 | 7 | 30));

/**
 * The owner shares the profile with a doctor or a viewer by username (Phase 7.1): read-only,
 * the whole profile, from the moment they accept until the chosen day or until revoked; who
 * has it now, open invitations, ending access, and who opened it on which days.
 */
export default function SharesScreen() {
  const t = useTranslations("app.shares");
  const tc = useTranslations("app.common");
  const p = usePalette();
  const errorText = useErrorText();
  const { patients, own: active } = useRecordProfile();
  // pinned: an invitation never goes to a profile other than the one this screen opened on
  const { pinned: own, changed } = usePinnedProfile(active);
  const isOwner = own?.access_level === "owner";
  const list = useShares(own?.id, { enabled: isOwner });
  const views = useShareViews(own?.id, { enabled: isOwner });
  const invite = useInviteShare(own?.id ?? "");
  const cancel = useCancelShareInvitation(own?.id ?? "");
  const end = useEndShare(own?.id ?? "");
  const [username, setUsername] = useState("");
  const [level, setLevel] = useState<ShareLevel>("doctor");
  const [duration, setDuration] = useState<Duration>("7");
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
  if (list.isPending) return <LoadingView />;
  if (!list.data) {
    return <RetryView text={errorText(list.error)} onRetry={() => void list.refetch()} />;
  }

  const levelText = (l: ShareLevel) => t(`level.${l}`);
  const daysText = (days: number | null | undefined) =>
    days ? t("duration.days", { n: days }) : t("duration.open");
  const name = username.trim().toLowerCase();
  const valid = USERNAME.test(name);
  const send = () =>
    Alert.alert(
      t("invite.checkTitle"),
      t("invite.checkBody", {
        username: name,
        level: levelText(level),
        duration: daysText(toDays(duration)),
      }),
      [
        { text: tc("cancel"), style: "cancel" },
        {
          text: t("invite.send"),
          onPress: () => {
            setSent(false);
            invite.mutate(
              { username: name, level, days: toDays(duration) },
              {
                onSuccess: () => {
                  setSent(true);
                  setUsername("");
                },
              },
            );
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
  const card = [styles.card, { backgroundColor: p.surface, borderColor: p.border }];

  return (
    <Screen>
      <ProfileBanner />
      <Paragraph>{t("intro")}</Paragraph>

      <Title>{t("listTitle")}</Title>
      {list.data.shares.length === 0 && <Paragraph muted>{t("none")}</Paragraph>}
      {list.data.shares.map((s) => (
        <View key={s.user_id} style={card} testID={`share-${s.user_id}`}>
          <Text style={[styles.name, { color: p.text }]}>{s.display_name}</Text>
          <Paragraph>{levelText(s.level)}</Paragraph>
          <Paragraph muted>
            {s.expires_at ? t("until", { date: formatDateTime(s.expires_at) }) : t("untilRevoked")}
          </Paragraph>
          <Paragraph muted>
            {s.last_viewed_at
              ? t("lastViewed", { date: formatDateTime(s.last_viewed_at) })
              : t("notViewed")}
          </Paragraph>
          <Button
            variant="danger"
            label={t("end.button")}
            accessibilityLabel={t("end.title", { name: s.display_name })}
            disabled={end.isPending}
            onPress={() => confirmEnd(s.user_id, s.display_name)}
          />
        </View>
      ))}

      {list.data.invitations.length > 0 && <Title>{t("pendingTitle")}</Title>}
      {list.data.invitations.map((i) => (
        <View key={i.id} style={card}>
          <Text style={[styles.name, { color: p.text }]}>{i.username}</Text>
          <Paragraph>
            {t("pendingRow", { level: levelText(i.level), duration: daysText(i.access_days) })}
          </Paragraph>
          <Paragraph muted>{t("expires", { date: formatDate(i.expires_at) })}</Paragraph>
          <Button
            variant="secondary"
            label={t("cancelInvite")}
            accessibilityLabel={t("cancelInviteLabel", { username: i.username })}
            disabled={cancel.isPending}
            onPress={() =>
              Alert.alert(
                t("cancelInviteLabel", { username: i.username }),
                undefined,
                [
                  { text: tc("cancel"), style: "cancel" },
                  { text: t("cancelInvite"), onPress: () => cancel.mutate(i.id) },
                ],
                { cancelable: true },
              )
            }
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
        testID="share-username"
      />
      <Segmented
        label={t("invite.level")}
        options={LEVELS}
        value={level}
        labelOf={levelText}
        onSelect={setLevel}
        testID="share-level"
      />
      <Paragraph muted>{t(`levelHint.${level}`)}</Paragraph>
      <Segmented
        label={t("invite.duration")}
        options={DURATIONS}
        value={duration}
        labelOf={(d) => daysText(toDays(d))}
        onSelect={setDuration}
        testID="share-duration"
      />
      <Button
        label={t("invite.button")}
        disabled={!valid || invite.isPending}
        busy={invite.isPending}
        onPress={send}
      />
      {sent && <FormMessage kind="success" text={t("invite.sent")} />}
      {invite.isError && <FormMessage kind="error" text={errorText(invite.error)} />}
      {(cancel.isError || end.isError) && (
        <FormMessage kind="error" text={errorText(cancel.error ?? end.error)} />
      )}

      <Title>{t("views.title")}</Title>
      <Paragraph muted>{t("views.hint")}</Paragraph>
      {views.isPending && <InlineLoading />}
      {views.isError && <FormMessage kind="error" text={errorText(views.error)} />}
      {views.data?.length === 0 && <Paragraph muted>{t("views.none")}</Paragraph>}
      {views.data?.map((v) => (
        <Paragraph key={`${v.user_id}-${v.day}`}>
          {t("views.row", {
            name: v.display_name,
            day: formatDate(v.day),
            first: formatDateTime(v.first_at),
            last: formatDateTime(v.last_at),
          })}
        </Paragraph>
      ))}
    </Screen>
  );
}

const styles = StyleSheet.create({
  card: { borderWidth: 1, borderRadius: radius.md, padding: space.md, gap: space.sm },
  name: { fontSize: fontSize.body, fontWeight: "700" },
});
