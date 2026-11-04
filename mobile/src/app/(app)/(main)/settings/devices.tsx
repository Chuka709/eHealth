import { feedbackGlyph, fontSize, radius, space } from "@labtrack/shared";
import { useState } from "react";
import { Alert, StyleSheet, Text, View } from "react-native";
import { useTranslations } from "use-intl";

import { Button } from "@/components/button";
import { FormMessage } from "@/components/form-message";
import { Screen } from "@/components/screen";
import { LoadingView, RetryView } from "@/components/state-view";
import { Paragraph } from "@/components/text";
import { signOut } from "@/features/auth/session";
import {
  type DeviceSession,
  useRevokeSession,
  useSessions,
} from "@/features/sessions/use-sessions";
import { formatDateTime } from "@/lib/dates";
import { useErrorText } from "@/lib/use-error-text";
import { usePalette } from "@/theme/use-palette";

export default function DevicesScreen() {
  const t = useTranslations("app");
  const errorText = useErrorText();
  const sessions = useSessions();
  const revoke = useRevokeSession();
  const [revoked, setRevoked] = useState<string | null>(null);

  if (sessions.isPending) return <LoadingView />;
  if (!sessions.data) {
    return <RetryView text={errorText(sessions.error)} onRetry={() => void sessions.refetch()} />;
  }
  const others = sessions.data.filter((s) => !s.current);

  const signOutThis = () =>
    Alert.alert(
      t("settings.signOutConfirmTitle"),
      t("settings.signOutConfirmBody"),
      [
        { text: t("common.cancel"), style: "cancel" },
        { text: t("settings.signOut"), style: "destructive", onPress: () => void signOut() },
      ],
      { cancelable: true },
    );
  const signOutOther = (session: DeviceSession, name: string) =>
    Alert.alert(
      t("devices.confirmTitle"),
      t("devices.confirmBody", { device: name }),
      [
        { text: t("common.cancel"), style: "cancel" },
        {
          text: t("devices.signOutDevice"),
          style: "destructive",
          onPress: () => {
            setRevoked(null);
            revoke.mutate(session.id, { onSuccess: () => setRevoked(name) });
          },
        },
      ],
      { cancelable: true },
    );

  return (
    <Screen>
      <Paragraph>{t("devices.intro")}</Paragraph>
      {revoked && <FormMessage kind="success" text={t("devices.revoked", { device: revoked })} />}
      {revoke.isError && <FormMessage kind="error" text={errorText(revoke.error)} />}
      {sessions.data.map((session) => (
        <DeviceCard
          key={session.id}
          session={session}
          busy={revoke.isPending && revoke.variables === session.id}
          onSignOut={(name) => (session.current ? signOutThis() : signOutOther(session, name))}
        />
      ))}
      {others.length === 0 && <Paragraph muted>{t("devices.none")}</Paragraph>}
    </Screen>
  );
}

function DeviceCard({
  session,
  busy,
  onSignOut,
}: {
  session: DeviceSession;
  busy: boolean;
  onSignOut: (name: string) => void;
}) {
  const t = useTranslations("app.devices");
  const p = usePalette();
  const platform =
    session.platform === "ios" || session.platform === "android" || session.platform === "web"
      ? t(session.platform)
      : null;
  const name = session.device_name ?? platform ?? t("unknownDevice");
  const details = [
    session.current ? t("thisDevice") : null,
    session.device_name ? platform : null,
    session.last_used_at ? t("lastUsed", { date: formatDateTime(session.last_used_at) }) : null,
    t("since", { date: formatDateTime(session.created_at) }),
  ].filter((line): line is string => Boolean(line));
  return (
    <View style={[styles.card, { backgroundColor: p.surface, borderColor: p.border }]}>
      {/* One stop for screen readers: name and details together; the button stays separate. */}
      <View accessible accessibilityLabel={[name, ...details].join(". ")} style={styles.info}>
        <Text style={[styles.name, { color: p.text }]}>{name}</Text>
        {session.current && (
          <View style={[styles.badge, { backgroundColor: p.feedback.success.bg }]}>
            <Text style={[styles.badgeText, { color: p.feedback.success.fg }]}>
              {`${feedbackGlyph.success} ${t("thisDevice")}`}
            </Text>
          </View>
        )}
        {details
          .filter((line) => line !== t("thisDevice"))
          .map((line) => (
            <Paragraph key={line} muted>
              {line}
            </Paragraph>
          ))}
      </View>
      <Button
        variant={session.current ? "danger" : "secondary"}
        label={session.current ? t("signOutThis") : t("signOutDevice")}
        accessibilityLabel={
          session.current ? t("signOutThis") : t("signOutDeviceLabel", { device: name })
        }
        busy={busy}
        onPress={() => onSignOut(name)}
      />
    </View>
  );
}

const styles = StyleSheet.create({
  card: {
    gap: space.sm,
    padding: space.md,
    borderRadius: radius.md,
    borderWidth: StyleSheet.hairlineWidth * 2,
  },
  info: { gap: space.xs },
  name: { fontSize: fontSize.bodyLarge, fontWeight: "600" },
  badge: {
    alignSelf: "flex-start",
    paddingHorizontal: space.sm,
    paddingVertical: space.xs,
    borderRadius: radius.sm,
  },
  badgeText: { fontSize: fontSize.caption, fontWeight: "600" },
});
