import { fontSize, minTouchTarget, radius, space } from "@labtrack/shared";
import { useRouter } from "expo-router";
import { memo, useCallback, useEffect, useMemo, useState } from "react";
import { FlatList, Platform, Pressable, StyleSheet, View } from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { useTranslations } from "use-intl";

import { Text } from "@/components/app-text";
import { Button } from "@/components/button";
import { MultiChoices, SelectList } from "@/components/choices";
import { Spinner } from "@/components/spinner";
import { LoadingView } from "@/components/state-view";
import { Paragraph, Title } from "@/components/text";
import { useRecordProfile } from "@/features/health/record-screens";
import {
  GROUPS,
  type Group,
  sectionOf,
  type TimelineItem,
  useLabs,
  useTimeline,
} from "@/features/timeline/use-timeline";
import { formatDate, formatDateTime } from "@/lib/dates";
import { useErrorText } from "@/lib/use-error-text";
import { usePalette } from "@/theme/use-palette";

type Row = { type: "section"; key: string } | { type: "item"; item: TimelineItem };
const ALL = "__all__";

/**
 * One timeline (docs/08 "Цагийн хэлхээс"; Phase 6.5-6.9; H34): transplants, medicines started,
 * stopped (the first day no longer taken - Q21) or changed (dose or schedule), clinical events
 * and confirmed lab reports, newest first, by month - a transplant known only to the year sits
 * under its year, never a month. Entries dated after today say "Төлөвлөсөн". A report says how
 * many results it has, how many were marked outside the range and how many had no range -
 * counts, never "all fine". Filters by kind and, for reports, by lab; "Харьцуулах" picks two
 * reports to see side by side. Nothing is judged or computed here (rule 6, 10b).
 */
export default function TimelineScreen() {
  const t = useTranslations("app.timeline");
  const errorText = useErrorText();
  const router = useRouter();
  const p = usePalette();
  const { own } = useRecordProfile();
  const [groups, setGroups] = useState<Group[]>([...GROUPS]);
  const [lab, setLab] = useState<string>(ALL);
  const [picking, setPicking] = useState(false);
  const [picked, setPicked] = useState<string[]>([]);
  const labs = useLabs(own?.id);
  const timeline = useTimeline(own?.id, groups, lab === ALL ? null : lab);

  const rows = useMemo<Row[]>(() => {
    const out: Row[] = [];
    let last = "";
    for (const page of timeline.data?.pages ?? []) {
      for (const item of page.items) {
        const section = sectionOf(item);
        if (section !== last) {
          out.push({ type: "section", key: section });
          last = section;
        }
        out.push({ type: "item", item });
      }
    }
    return out;
  }, [timeline.data]);

  // another filter: what was picked may no longer be listed
  // biome-ignore lint/correctness/useExhaustiveDependencies: reset on a filter change only
  useEffect(() => setPicked([]), [groups, lab]);
  const pick = useCallback(
    (id: string) =>
      setPicked((cur) =>
        cur.includes(id) ? cur.filter((x) => x !== id) : cur.length < 2 ? [...cur, id] : cur,
      ),
    [],
  );

  // only the very first load replaces the screen; later the filters stay put
  if (!own || (timeline.isPending && groups.length > 0 && !timeline.data && !timeline.isError)) {
    return <LoadingView />;
  }
  const toggle = (g: Group) =>
    setGroups((cur) => (cur.includes(g) ? cur.filter((x) => x !== g) : [...cur, g]));
  const labOptions = [ALL, ...(labs.data ?? []).map((l) => l.lab_name)];

  const header = (
    <View style={styles.header}>
      <MultiChoices
        compact
        label={t("show")}
        options={GROUPS}
        values={groups}
        labelOf={(g) => t(`groups.${g}`)}
        onToggle={toggle}
      />
      {labOptions.length > 2 && groups.includes("report") && (
        <SelectList
          label={t("lab")}
          options={labOptions}
          value={lab}
          labelOf={(l) => (l === ALL ? t("allLabs") : l)}
          onSelect={setLab}
        />
      )}
      {groups.includes("report") && !picking && (
        <Button variant="secondary" label={t("compare")} onPress={() => setPicking(true)} />
      )}
      {timeline.isError && !timeline.isFetchNextPageError && (
        <RetryLine text={errorText(timeline.error)} onRetry={() => void timeline.refetch()} />
      )}
      {groups.length === 0 && <Paragraph muted>{t("noneShown")}</Paragraph>}
    </View>
  );

  return (
    <View style={styles.fill}>
      <FlatList
        testID="timeline-screen"
        data={rows}
        keyExtractor={(r) => (r.type === "section" ? `s-${r.key}` : `${r.item.kind}-${r.item.id}`)}
        renderItem={({ item: r }) =>
          r.type === "section" ? (
            <SectionHeader section={r.key} />
          ) : (
            <ItemRow
              item={r.item}
              picking={picking}
              picked={picked.includes(r.item.id)}
              onPick={pick}
            />
          )
        }
        ListHeaderComponent={header}
        ListEmptyComponent={
          groups.length > 0 ? <Paragraph muted>{t("empty")}</Paragraph> : undefined
        }
        ListFooterComponent={
          timeline.isFetchingNextPage ? (
            <Spinner />
          ) : timeline.isFetchNextPageError ? (
            <RetryLine
              text={errorText(timeline.error)}
              onRetry={() => void timeline.fetchNextPage()}
            />
          ) : undefined
        }
        onEndReached={() => {
          if (timeline.hasNextPage && !timeline.isFetchingNextPage) void timeline.fetchNextPage();
        }}
        onEndReachedThreshold={0.5}
        style={{ backgroundColor: p.background }}
        contentContainerStyle={styles.content}
        contentInsetAdjustmentBehavior="automatic"
      />
      {picking && (
        // within thumb reach while scrolling to pick (one-handed use)
        <SafeAreaView
          edges={["bottom"]}
          style={[styles.panel, { backgroundColor: p.surface, borderTopColor: p.border }]}
        >
          <Text accessibilityLiveRegion="polite" style={[styles.meta, { color: p.text }]}>
            {t("pickTwo")}
          </Text>
          <Button
            label={t("compareGo", { n: picked.length })}
            disabled={picked.length !== 2}
            onPress={() =>
              router.push({ pathname: "/reports/compare", params: { a: picked[0], b: picked[1] } })
            }
          />
          <Button
            variant="link"
            label={t("compareCancel")}
            onPress={() => {
              setPicking(false);
              setPicked([]);
            }}
          />
        </SafeAreaView>
      )}
    </View>
  );
}

function RetryLine({ text, onRetry }: { text: string; onRetry: () => void }) {
  const ts = useTranslations("status");
  return (
    <View style={styles.compare}>
      <Paragraph muted>{text}</Paragraph>
      <Button variant="link" label={ts("retry")} onPress={onRetry} />
    </View>
  );
}

function SectionHeader({ section }: { section: string }) {
  const t = useTranslations("app.timeline");
  const [y, m] = section.split("-");
  return (
    <View style={styles.section}>
      <Title>{m ? t("month", { year: y, month: Number(m) }) : t("year", { year: y })}</Title>
    </View>
  );
}

const ItemRow = memo(function ItemRow({
  item,
  picking,
  picked,
  onPick,
}: {
  item: TimelineItem;
  picking: boolean;
  picked: boolean;
  onPick: (id: string) => void;
}) {
  const t = useTranslations("app.timeline");
  const ta = useTranslations("app");
  const router = useRouter();
  const p = usePalette();
  const planned = item.planned && item.kind !== "report" ? t("planned") : null;
  const { title, lines } = describe(item, t, ta, planned !== null);
  const when = dayText(item, t);
  const pickable = picking && item.kind === "report";
  const inert = picking && !pickable;
  const open = () => {
    if (inert) return;
    if (pickable) return onPick(item.id);
    switch (item.kind) {
      case "report":
        return router.push(`/results/${item.ref_id ?? item.id}`);
      case "transplant":
        return router.push({ pathname: "/transplants/[id]", params: { id: item.id } });
      case "event":
        return router.push({ pathname: "/events/[id]", params: { id: item.id } });
      case "regimen_changed":
        return item.ref_id
          ? router.push({ pathname: "/meds/[id]", params: { id: item.ref_id } })
          : undefined;
      default:
        return router.push({ pathname: "/meds/[id]", params: { id: item.id } });
    }
  };
  return (
    <Pressable
      onPress={open}
      accessibilityRole={pickable ? "checkbox" : "button"}
      accessibilityState={pickable ? { checked: picked } : inert ? { disabled: true } : undefined}
      disabled={inert}
      accessibilityLabel={[planned, when, title, ...lines].filter(Boolean).join(". ")}
      style={[
        styles.row,
        { borderTopColor: p.border },
        picked && { backgroundColor: p.primarySoft },
        inert && styles.inert,
      ]}
      testID={`tl-${item.kind}-${item.id}`}
    >
      <View style={styles.line}>
        <Text style={[styles.when, { color: p.textMuted }]}>
          {pickable ? `${picked ? "☑" : "☐"} ` : ""}
          {planned ? `${planned} · ${when}` : when}
        </Text>
      </View>
      <Text style={[styles.title, { color: p.text }]}>{title}</Text>
      {lines.map((l) => (
        <Text key={l} style={[styles.meta, { color: p.textMuted }]}>
          {l}
        </Text>
      ))}
    </Pressable>
  );
});

type T = ReturnType<typeof useTranslations<"app.timeline">>;
type TA = ReturnType<typeof useTranslations<"app">>;

/** The day as it is known: a report with a time keeps it, a transplant known only to the
 * month/year says so (H24). */
function dayText(item: TimelineItem, t: T): string {
  const [y, m] = item.day.split("-");
  if (item.kind === "transplant" && item.precision === "year") return t("dayYear", { year: y });
  if (item.kind === "transplant" && item.precision === "month") {
    return t("dayMonth", { year: y, month: m });
  }
  if (item.kind === "report" && item.precision === "minute" && item.at) {
    return formatDateTime(item.at);
  }
  return formatDate(item.day);
}

function describe(
  item: TimelineItem,
  t: T,
  ta: TA,
  ahead: boolean,
): { title: string; lines: string[] } {
  switch (item.kind) {
    case "transplant": {
      const organ = ta(`transplant.organ.${item.title}` as "transplant.title");
      const lines =
        item.detail && item.detail !== "functioning"
          ? [t("graft", { status: ta(`emergency.graft.${item.detail}` as "emergency.title") })]
          : [];
      return { title: t("transplant", { organ }), lines };
    }
    case "medication_started":
      return { title: t(ahead ? "startsAhead" : "started", { name: item.title ?? "" }), lines: [] };
    case "medication_stopped":
      // the stop day is the first day no longer taken (Q21): said so, not "stopped on"
      return { title: t(ahead ? "stopsAhead" : "stopped", { name: item.title ?? "" }), lines: [] };
    case "regimen_changed":
      return {
        title: t(ahead ? "changesAhead" : "changed", { name: item.title ?? "" }),
        lines: [],
      };
    case "event": {
      const kind = ta(`health.event.kinds.${item.detail}` as "health.title");
      const lines = [kind];
      if (item.until) {
        // an end still ahead is said in the future tense
        const today = new Intl.DateTimeFormat("en-CA", { timeZone: "Asia/Ulaanbaatar" }).format(
          new Date(),
        );
        const key = item.until > today ? "untilAhead" : "until";
        lines.push(t(key, { date: formatDate(item.until) }));
      }
      return { title: item.title ?? kind, lines };
    }
    default: {
      const lines = [
        t("results", { count: item.results ?? 0 }),
        t("flagged", { flagged: item.flagged ?? 0, count: item.results ?? 0 }),
      ];
      if ((item.unflagged ?? 0) > 0) lines.push(t("unflagged", { count: item.unflagged ?? 0 }));
      if (item.detail === "typed") lines.push(t("typed"));
      return { title: item.title ?? t("report"), lines };
    }
  }
}

const styles = StyleSheet.create({
  content: { padding: space.lg },
  header: { gap: space.md, paddingBottom: space.md },
  compare: { gap: space.sm },
  section: { paddingTop: space.lg, paddingBottom: space.xs },
  row: {
    gap: space.xs,
    paddingVertical: space.sm,
    paddingHorizontal: space.xs,
    borderTopWidth: StyleSheet.hairlineWidth,
    borderRadius: radius.sm,
    minHeight: Platform.OS === "ios" ? minTouchTarget.ios : minTouchTarget.android,
  },
  line: { flexDirection: "row", gap: space.sm },
  when: { fontSize: fontSize.body, fontVariant: ["tabular-nums"] },
  title: { fontSize: fontSize.body, fontWeight: "600" },
  meta: { fontSize: fontSize.body },
  fill: { flex: 1 },
  inert: { opacity: 0.5 },
  panel: {
    gap: space.xs,
    paddingHorizontal: space.lg,
    paddingTop: space.sm,
    borderTopWidth: StyleSheet.hairlineWidth,
  },
});
