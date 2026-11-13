import { flagGlyph, fontSize, radius, space } from "@labtrack/shared";
import { useRouter } from "expo-router";
import { Alert, Linking, Pressable, StyleSheet, View } from "react-native";
import { useTranslations } from "use-intl";

import { Text } from "@/components/app-text";
import { Button } from "@/components/button";
import { FormMessage } from "@/components/form-message";
import { Paragraph, Title } from "@/components/text";
import { CRITICAL_FLAGS, flagKey, flagToken } from "@/features/review/flag";
import { formatDate, formatDateTime } from "@/lib/dates";
import { loading, OFFLINE_ERROR } from "@/lib/query-state";
import { useErrorText } from "@/lib/use-error-text";
import { usePalette } from "@/theme/use-palette";

import { Sparkline } from "./sparkline";
import { type DashboardCard, type LatestValue, percentText, useDashboard } from "./use-dashboard";

/**
 * Home's lab part (docs/06 §1, docs/08 "Нүүр"; Phase 6.8): values the results marked outside
 * their range - only the result's own ranges or the lab's critical mark, from the last 90 days,
 * critical first (H32) - as short rows, with what to do when one is critical (H5); then the key
 * cards: the latest confirmed value as printed, its flag in colour + glyph + text, the printed
 * range and date, the change from the previous value (a plain number, the previous value as ITS
 * result printed it) and a small line. Confirmed values only (rule 4); nothing is computed here
 * (rule 6). A row or card opens the test's trend.
 */
export function LabSections({ patientId, canEdit }: { patientId: string; canEdit: boolean }) {
  const t = useTranslations("app.home.lab");
  const ts = useTranslations("status");
  const tr = useTranslations("app.upload.review");
  const errorText = useErrorText();
  const router = useRouter();
  const p = usePalette();
  const dashboard = useDashboard(patientId);
  // a cached answer from an older app version may lack a field: never a crash on Home
  const data =
    dashboard.data && Array.isArray(dashboard.data.cards) && Array.isArray(dashboard.data.attention)
      ? dashboard.data
      : undefined;
  if (loading(dashboard)) {
    return <Paragraph muted>{t("loading")}</Paragraph>;
  }
  if (!data) {
    return (
      <>
        <Title>{t("cards")}</Title>
        <FormMessage kind="error" text={errorText(dashboard.error ?? OFFLINE_ERROR)} />
        <Button
          variant="link"
          label={ts("retry")}
          accessibilityLabel={`${t("cards")}. ${ts("retry")}`}
          onPress={() => void dashboard.refetch()}
        />
      </>
    );
  }
  const anyCritical = data.attention.some((a) => CRITICAL_FLAGS.has(a.latest.flag));
  // shown from the phone's copy while the server cannot be reached: say how old it is
  const stale = dashboard.isError && dashboard.dataUpdatedAt > 0;
  return (
    <>
      {stale && (
        <Paragraph muted>
          {t("stale", { when: formatDateTime(new Date(dashboard.dataUpdatedAt).toISOString()) })}
        </Paragraph>
      )}
      {data.attention.length > 0 && (
        <View style={styles.section} testID="home-attention">
          <Title>{t("attention")}</Title>
          <Paragraph muted>{t("attentionHint")}</Paragraph>
          {anyCritical && (
            <View
              style={[styles.help, { borderColor: p.flag.critical.bg }]}
              testID="home-critical-help"
            >
              <Text style={[styles.meta, { color: p.text }]}>{t("criticalHelp")}</Text>
              <Button
                variant="secondary"
                label={tr("call103")}
                onPress={() =>
                  void Linking.openURL("tel:103").catch(() => Alert.alert(tr("call103"), "103"))
                }
              />
            </View>
          )}
          {data.attention.map((a) => (
            <AttentionRow key={a.test_code} code={a.test_code} name={a.name_mn} latest={a.latest} />
          ))}
        </View>
      )}
      <View style={styles.section} testID="home-cards">
        <Title>{t("cards")}</Title>
        {!data.custom && data.cards.length > 0 && <Paragraph muted>{t("defaultsNote")}</Paragraph>}
        {data.cards.length === 0 ? (
          <Paragraph muted>{data.custom ? t("noneChosen") : t("noDefaults")}</Paragraph>
        ) : (
          data.cards.map((c) => <ValueCard key={c.test_code} card={c} />)
        )}
        {canEdit && (
          <Button
            variant="link"
            label={t("edit")}
            onPress={() => router.push("/dashboard/cards")}
          />
        )}
      </View>
    </>
  );
}

function useValueTexts(latest: LatestValue) {
  const t = useTranslations("app.home.lab");
  const tr = useTranslations("app.upload.review");
  const token = flagToken(latest.flag);
  return {
    token,
    flagText: tr(`flags.${flagKey(latest.flag)}` as "flags.unknown"),
    value: [latest.raw_value, latest.raw_unit].filter(Boolean).join(" "),
    date: formatDate(latest.collected_at),
    checkSource: latest.possibly_critical && token !== "critical" ? t("checkSource") : null,
  };
}

function FlagChip({ token, text }: { token: ReturnType<typeof flagToken>; text: string }) {
  const p = usePalette();
  const colour = p.flag[token];
  return (
    <View style={[styles.flag, { backgroundColor: colour.bg }]}>
      <Text style={[styles.meta, styles.strong, { color: colour.fg }]}>
        {`${flagGlyph[token]} ${text}`}
      </Text>
    </View>
  );
}

/** A short row: name, value, flag, date (the card below holds the rest). */
function AttentionRow({ code, name, latest }: { code: string; name: string; latest: LatestValue }) {
  const t = useTranslations("app.home.lab");
  const router = useRouter();
  const p = usePalette();
  const v = useValueTexts(latest);
  return (
    <Pressable
      onPress={() => router.push(`/trends/${code}`)}
      accessibilityRole="button"
      accessibilityLabel={[name, v.value, v.flagText, v.checkSource, v.date]
        .filter(Boolean)
        .join(". ")}
      accessibilityHint={t("openTrend")}
      style={[styles.row, { borderTopColor: p.border }]}
      testID={`attention-${code}`}
    >
      <View style={styles.line}>
        <Text style={[styles.name, { color: p.text }]}>{name}</Text>
        <Text style={[styles.rowValue, { color: p.text }]}>{v.value}</Text>
      </View>
      <View style={styles.line}>
        <FlagChip token={v.token} text={v.flagText} />
        <Text style={[styles.meta, { color: p.textMuted }]}>{v.date}</Text>
      </View>
      {v.checkSource && <Text style={[styles.meta, { color: p.text }]}>{v.checkSource}</Text>}
    </Pressable>
  );
}

function ValueCard({ card }: { card: DashboardCard }) {
  const t = useTranslations("app.home.lab");
  const router = useRouter();
  const p = usePalette();
  const open = () => router.push(`/trends/${card.test_code}`);
  if (card.latest === null) {
    return (
      <Pressable
        onPress={open}
        accessibilityRole="button"
        accessibilityLabel={`${card.name_mn}. ${t("noValue")}`}
        accessibilityHint={t("openTrend")}
        style={[styles.card, { backgroundColor: p.surface, borderColor: p.border }]}
        testID={`card-${card.test_code}`}
      >
        <Text style={[styles.name, { color: p.text }]}>{card.name_mn}</Text>
        <Text style={[styles.meta, { color: p.textMuted }]}>{t("noValue")}</Text>
      </Pressable>
    );
  }
  return <ValueCardFilled card={card} latest={card.latest} onPress={open} />;
}

function ValueCardFilled({
  card,
  latest,
  onPress,
}: {
  card: DashboardCard;
  latest: LatestValue;
  onPress: () => void;
}) {
  const t = useTranslations("app.home.lab");
  const p = usePalette();
  const v = useValueTexts(latest);
  const rangeAndDate = [
    latest.ref_text ? t("range", { range: latest.ref_text }) : t("noRange"),
    v.date,
  ].join(" · ");
  const previous = card.change
    ? [card.change.previous_raw_value, card.change.previous_raw_unit].filter(Boolean).join(" ")
    : "";
  const change =
    card.change && previous
      ? t("change", {
          percent: percentText(card.change.percent),
          date: formatDate(card.change.previous_collected_at),
          value: previous,
        })
      : null;
  // the line is in the catalog unit: drawn only when the latest value is in it too
  const showSpark = card.spark.length > 1 && card.spark_unit === latest.unit;
  return (
    <Pressable
      onPress={onPress}
      accessibilityRole="button"
      accessibilityLabel={[card.name_mn, v.value, v.flagText, v.checkSource, rangeAndDate, change]
        .filter(Boolean)
        .join(". ")}
      accessibilityHint={t("openTrend")}
      style={[styles.card, { backgroundColor: p.surface, borderColor: p.border }]}
      testID={`card-${card.test_code}`}
    >
      <View style={styles.top}>
        <View style={styles.text}>
          <Text style={[styles.name, { color: p.text }]}>{card.name_mn}</Text>
          <Text style={[styles.value, { color: p.text }]}>{v.value}</Text>
        </View>
        {showSpark && <Sparkline spark={card.spark} />}
      </View>
      <FlagChip token={v.token} text={v.flagText} />
      {v.checkSource && <Text style={[styles.meta, { color: p.text }]}>{v.checkSource}</Text>}
      <Text style={[styles.meta, { color: p.textMuted }]}>{rangeAndDate}</Text>
      {change && (
        <Text style={[styles.meta, styles.tabular, { color: p.textMuted }]}>{change}</Text>
      )}
    </Pressable>
  );
}

const styles = StyleSheet.create({
  section: { gap: space.sm },
  help: { gap: space.sm, padding: space.md, borderRadius: radius.md, borderWidth: 2 },
  row: { gap: space.xs, paddingVertical: space.sm, borderTopWidth: StyleSheet.hairlineWidth },
  line: {
    flexDirection: "row",
    justifyContent: "space-between",
    alignItems: "center",
    gap: space.sm,
    flexWrap: "wrap",
  },
  card: {
    gap: space.xs,
    padding: space.md,
    borderRadius: radius.md,
    borderWidth: StyleSheet.hairlineWidth,
  },
  top: { flexDirection: "row", alignItems: "center", gap: space.sm },
  text: { flex: 1, gap: space.xs },
  name: { fontSize: fontSize.body, fontWeight: "600" },
  rowValue: { fontSize: fontSize.body, fontWeight: "700", fontVariant: ["tabular-nums"] },
  value: { fontSize: fontSize.bodyLarge, fontWeight: "700", fontVariant: ["tabular-nums"] },
  flag: { alignSelf: "flex-start", borderRadius: radius.sm, paddingHorizontal: space.sm },
  meta: { fontSize: fontSize.body },
  tabular: { fontVariant: ["tabular-nums"] },
  strong: { fontWeight: "600" },
});
