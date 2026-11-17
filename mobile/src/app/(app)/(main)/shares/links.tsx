import { fontSize, radius, space } from "@labtrack/shared";
import { useState } from "react";
import { Alert, Share, StyleSheet, View } from "react-native";
import { useTranslations } from "use-intl";
import { Text } from "@/components/app-text";

import { Button } from "@/components/button";
import { MultiChoices } from "@/components/choices";
import { FormMessage } from "@/components/form-message";
import { Screen } from "@/components/screen";
import { Segmented } from "@/components/segmented";
import { LoadingView, RetryView } from "@/components/state-view";
import { Paragraph, Title } from "@/components/text";
import { useRecordProfile } from "@/features/health/record-screens";
import { usePinnedProfile } from "@/features/records/active-profile";
import { ProfileBanner } from "@/features/records/profile-banner";
import { ProfileChanged } from "@/features/records/profile-changed";
import { QrCode } from "@/features/shares/qr-code";
import {
  linkState,
  SCOPES,
  type ShareLink,
  type ShareLinkCreated,
  type ShareScope,
  useCreateShareLink,
  useRevokeShareLink,
  useShareLinks,
  useShareLinkViews,
} from "@/features/shares/use-share-links";
import { formatDateTime } from "@/lib/dates";
import { shareLinkUrl } from "@/lib/share-base";
import { useErrorText } from "@/lib/use-error-text";
import { usePalette } from "@/theme/use-palette";

const DAYS = ["1", "7", "30"] as const;
const VIEWS = ["any", "1", "3", "10"] as const;
const PERIODS = ["all", "3", "12"] as const;
type Period = (typeof PERIODS)[number];

/** The first day of a period, as a calendar date on this phone (YYYY-MM-DD). */
function periodStart(period: Period, today: Date = new Date()): string | null {
  if (period === "all") return null;
  const d = new Date(today.getFullYear(), today.getMonth() - Number(period), today.getDate());
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
}

/**
 * Share links (Phase 7.6 over the 7.2 API): the owner picks sections, how long and how many
 * opens, and gets a link with a QR code and a 6-digit PIN shown once. The link opens on the web
 * viewer with the PIN; the owner sees each link's opens and revokes it at any time.
 */
export default function ShareLinksScreen() {
  const t = useTranslations("app.shareLinks");
  const tc = useTranslations("app.common");
  const p = usePalette();
  const errorText = useErrorText();
  const { patients, own: active } = useRecordProfile();
  const { pinned: own, changed } = usePinnedProfile(active);
  const isOwner = own?.access_level === "owner";
  const list = useShareLinks(own?.id, { enabled: isOwner });
  const create = useCreateShareLink(own?.id ?? "");
  const revoke = useRevokeShareLink(own?.id ?? "");
  const [scopes, setScopes] = useState<ShareScope[]>(["summary", "labs", "meds"]);
  const [days, setDays] = useState<(typeof DAYS)[number]>("7");
  const [views, setViews] = useState<(typeof VIEWS)[number]>("any");
  const [period, setPeriod] = useState<Period>("all");
  // the token and the PIN: in this state only, gone when the owner leaves the screen
  const [created, setCreated] = useState<ShareLinkCreated | null>(null);
  const [opened, setOpened] = useState<string | null>(null);

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

  if (created) {
    return (
      <Created
        link={created}
        onDone={() => {
          setCreated(null);
          create.reset(); // the token and the PIN leave memory too
        }}
      />
    );
  }

  if (list.isPending) return <LoadingView />;
  if (!list.data) {
    return <RetryView text={errorText(list.error)} onRetry={() => void list.refetch()} />;
  }

  const scopeText = (s: ShareScope) => t(`scope.${s}`);
  const daysText = (d: string) => t("days", { n: Number(d) });
  const viewsText = (v: string) => (v === "any" ? t("views.any") : t("views.n", { n: Number(v) }));
  const periodText = (v: Period) =>
    v === "all" ? t("period.all") : t("period.months", { n: Number(v) });
  const toggle = (s: ShareScope) =>
    setScopes((cur) => (cur.includes(s) ? cur.filter((x) => x !== s) : [...cur, s]));
  const chosen = SCOPES.filter((s) => scopes.includes(s));
  const make = () =>
    Alert.alert(
      t("create.checkTitle"),
      t("create.checkBody", {
        sections: chosen.map(scopeText).join(", "),
        days: daysText(days),
        views: viewsText(views),
        period: periodText(period),
      }),
      [
        { text: tc("cancel"), style: "cancel" },
        {
          text: t("create.confirm"),
          onPress: () =>
            create.mutate(
              {
                scopes: chosen,
                days: Number(days) as 1 | 7 | 30,
                max_views: views === "any" ? null : Number(views),
                date_from: periodStart(period),
                date_to: null,
              },
              { onSuccess: (link) => setCreated(link) },
            ),
        },
      ],
      { cancelable: true },
    );
  const confirmRevoke = (id: string) =>
    Alert.alert(
      t("revoke.title"),
      t("revoke.body"),
      [
        { text: tc("cancel"), style: "cancel" },
        { text: t("revoke.confirm"), style: "destructive", onPress: () => revoke.mutate(id) },
      ],
      { cancelable: true },
    );

  return (
    <Screen>
      <ProfileBanner />
      <Paragraph>{t("intro")}</Paragraph>

      <Title>{t("create.title")}</Title>
      <MultiChoices
        label={t("create.sections")}
        options={SCOPES}
        values={scopes}
        labelOf={scopeText}
        onToggle={toggle}
        error={chosen.length === 0 ? t("create.noSections") : undefined}
      />
      <Segmented
        label={t("create.days")}
        options={DAYS}
        value={days}
        labelOf={daysText}
        onSelect={setDays}
        testID="link-days"
        showLabel
      />
      <Segmented
        label={t("create.views")}
        options={VIEWS}
        value={views}
        labelOf={viewsText}
        onSelect={setViews}
        testID="link-views"
        showLabel
      />
      <Segmented
        label={t("create.period")}
        options={PERIODS}
        value={period}
        labelOf={periodText}
        onSelect={setPeriod}
        testID="link-period"
        showLabel
      />
      <Paragraph muted>{t("create.periodHint")}</Paragraph>
      <Button
        label={t("create.button")}
        disabled={chosen.length === 0 || create.isPending}
        busy={create.isPending}
        onPress={make}
      />
      {create.isError && <FormMessage kind="error" text={errorText(create.error)} />}

      <Title>{t("listTitle")}</Title>
      {list.data.length === 0 && <Paragraph muted>{t("none")}</Paragraph>}
      {revoke.isError && <FormMessage kind="error" text={errorText(revoke.error)} />}
      {list.data.map((link) => (
        <LinkCard
          key={link.id}
          link={link}
          patientId={own.id}
          scopeText={scopeText}
          showViews={opened === link.id}
          onToggleViews={() => setOpened(opened === link.id ? null : link.id)}
          onRevoke={() => confirmRevoke(link.id)}
          revoking={revoke.isPending}
          cardStyle={[styles.card, { backgroundColor: p.surface, borderColor: p.border }]}
        />
      ))}
    </Screen>
  );
}

function LinkCard({
  link,
  patientId,
  scopeText,
  showViews,
  onToggleViews,
  onRevoke,
  revoking,
  cardStyle,
}: {
  link: ShareLink;
  patientId: string;
  scopeText: (s: ShareScope) => string;
  showViews: boolean;
  onToggleViews: () => void;
  onRevoke: () => void;
  revoking: boolean;
  cardStyle: object[];
}) {
  const t = useTranslations("app.shareLinks");
  const p = usePalette();
  const errorText = useErrorText();
  const state = linkState(link);
  const views = useShareLinkViews(patientId, showViews ? link.id : null);
  const sections = SCOPES.filter((s) => link.scopes.includes(s))
    .map(scopeText)
    .join(", ");
  return (
    <View style={cardStyle} testID={`link-${link.id}`}>
      <Text style={[styles.name, { color: p.text }]}>{t(`state.${state}`)}</Text>
      <Paragraph>{sections}</Paragraph>
      <Paragraph muted>
        {state === "active"
          ? t("until", { date: formatDateTime(link.expires_at) })
          : t("made", { date: formatDateTime(link.created_at) })}
      </Paragraph>
      <Paragraph muted>
        {link.max_views === null
          ? t("opens", { n: link.view_count })
          : t("opensOf", { n: link.view_count, max: link.max_views })}
      </Paragraph>
      {link.last_viewed_at && (
        <Paragraph muted>
          {t("lastOpened", { date: formatDateTime(link.last_viewed_at) })}
        </Paragraph>
      )}
      {link.view_count > 0 && (
        <Button
          variant="secondary"
          label={showViews ? t("hideViews") : t("showViews")}
          onPress={onToggleViews}
        />
      )}
      {showViews && views.isPending && <LoadingInline />}
      {showViews && views.isError && <FormMessage kind="error" text={errorText(views.error)} />}
      {showViews &&
        views.data?.map((v, i) => (
          <Paragraph key={`${v.opened_at}-${i}`}>{formatDateTime(v.opened_at)}</Paragraph>
        ))}
      {state === "active" && (
        <Button
          variant="danger"
          label={t("revoke.button")}
          disabled={revoking}
          onPress={onRevoke}
        />
      )}
    </View>
  );
}

function LoadingInline() {
  const tc = useTranslations("app.common");
  return <Paragraph muted>{tc("loading")}</Paragraph>;
}

/** Shown once: the QR code and the link, the PIN apart, and a way to send the link alone. */
function Created({ link, onDone }: { link: ShareLinkCreated; onDone: () => void }) {
  const t = useTranslations("app.shareLinks.created");
  const p = usePalette();
  const url = shareLinkUrl(link.token);
  const pin = `${link.pin.slice(0, 3)} ${link.pin.slice(3)}`;
  return (
    <Screen>
      <ProfileBanner />
      <Title>{t("title")}</Title>
      <Paragraph>{t("how")}</Paragraph>
      <View style={styles.qr}>
        <QrCode value={url} size={240} label={t("qrLabel")} testID="link-qr" />
      </View>
      <Text
        style={[styles.url, { color: p.text }]}
        testID="link-url"
        accessibilityLabel={t("urlLabel")}
      >
        {url}
      </Text>
      <Button
        variant="secondary"
        label={t("send")}
        onPress={() => void Share.share({ message: url })}
      />
      <View style={[styles.card, { backgroundColor: p.surface, borderColor: p.border }]}>
        <Text style={[styles.pinLabel, { color: p.text }]}>{t("pin")}</Text>
        <Text
          style={[styles.pin, { color: p.text }]}
          accessibilityLabel={t("pinLabel", { pin: link.pin.split("").join(" ") })}
          testID="link-pin"
        >
          {pin}
        </Text>
        <Paragraph>{t("pinHint")}</Paragraph>
      </View>
      <Paragraph muted>{t("until", { date: formatDateTime(link.expires_at) })}</Paragraph>
      <FormMessage kind="warning" text={t("once")} />
      <Button label={t("done")} onPress={onDone} />
    </Screen>
  );
}

const styles = StyleSheet.create({
  card: { borderWidth: 1, borderRadius: radius.md, padding: space.md, gap: space.sm },
  name: { fontSize: fontSize.body, fontWeight: "700" },
  qr: { alignItems: "center", paddingVertical: space.md },
  url: { fontSize: fontSize.caption },
  pinLabel: { fontSize: fontSize.body },
  pin: {
    fontSize: fontSize.display,
    fontWeight: "700",
    letterSpacing: 4,
    fontVariant: ["tabular-nums"],
  },
});
