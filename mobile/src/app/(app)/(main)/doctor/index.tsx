import { fontSize, radius, space } from "@labtrack/shared";
import { useState } from "react";
import { Alert, StyleSheet, View } from "react-native";
import { useTranslations } from "use-intl";
import { Text } from "@/components/app-text";

import { Button } from "@/components/button";
import { Choices } from "@/components/choices";
import { dayOf, PickerField } from "@/components/date-field";
import { FormMessage } from "@/components/form-message";
import { Screen } from "@/components/screen";
import { Segmented } from "@/components/segmented";
import { LoadingView, RetryView } from "@/components/state-view";
import { Paragraph, Title } from "@/components/text";
import { TextField } from "@/components/text-field";
import {
  type LevelStats,
  type Target,
  useAddNote,
  useDoctorNotes,
  useEndTarget,
  useLevelStats,
  useMarkSteroidCard,
  useRemoveNote,
  useSetTarget,
  useSteroidCard,
  useTargets,
} from "@/features/clinician/use-clinician";
import { useRecordProfile } from "@/features/health/record-screens";
import { usePinnedProfile } from "@/features/records/active-profile";
import { ProfileBanner } from "@/features/records/profile-banner";
import { ProfileChanged } from "@/features/records/profile-changed";
import { useLabTests } from "@/features/review/use-review";
import { formatDate, formatDateTime } from "@/lib/dates";
import { useErrorText } from "@/lib/use-error-text";
import { usePalette } from "@/theme/use-palette";

const MONTHS = ["6", "12", "24"] as const;
const LEFT_OUT = [
  "bounds_left_out",
  "not_numeric_left_out",
  "other_unit_left_out",
  "no_date_left_out",
  "early_left_out",
  "duplicates_left_out",
  "same_day_left_out",
] as const;

/**
 * The treating doctor's targets and notes, and the tacrolimus level statistics (Phase 7.6):
 * read by everyone who can open the profile, written only by a doctor it was shared with.
 * Numbers as the server gives them; no threshold, colour or "good/bad" (rule 10b, H15).
 */
export default function DoctorScreen() {
  const t = useTranslations("app.clinician");
  const errorText = useErrorText();
  const { patients, own: active } = useRecordProfile();
  const { pinned: own, changed } = usePinnedProfile(active);
  const targets = useTargets(own?.id);
  const notes = useDoctorNotes(own?.id);
  const tests = useLabTests();

  if (changed) return <ProfileChanged />;
  if (patients.isPending) return <LoadingView />;
  if (!own) {
    return <RetryView text={errorText(patients.error)} onRetry={() => void patients.refetch()} />;
  }
  const isDoctor = own.access_level === "doctor";
  const nameOf = (code: string) => tests.data?.find((x) => x.code === code)?.name_mn ?? code;

  return (
    <Screen>
      <ProfileBanner />
      <Paragraph>{isDoctor ? t("introDoctor") : t("intro")}</Paragraph>

      {/* for the doctor only until the explanation is reviewed (Q12 ★): the patient sees it
          then, with CV% alone (Q63-7 ★) */}
      {isDoctor && <LevelCard patientId={own.id} />}

      <SteroidCardSection
        patientId={own.id}
        isDoctor={isDoctor}
        canMark={isDoctor || own.access_level === "owner"}
      />

      <Title>{t("targets.title")}</Title>
      <Paragraph muted>{t("targets.hint")}</Paragraph>
      {targets.isPending && <LoadingView />}
      {targets.isError && (
        <RetryView text={errorText(targets.error)} onRetry={() => void targets.refetch()} />
      )}
      {targets.data?.length === 0 && <Paragraph muted>{t("targets.none")}</Paragraph>}
      {targets.data?.map((target) => (
        <TargetCard
          key={target.id}
          target={target}
          name={nameOf(target.test_code)}
          patientId={own.id}
          canEnd={isDoctor}
        />
      ))}
      {isDoctor && <TargetForm patientId={own.id} />}

      <Title>{t("notes.title")}</Title>
      {notes.isPending && <LoadingView />}
      {notes.isError && (
        <RetryView text={errorText(notes.error)} onRetry={() => void notes.refetch()} />
      )}
      {notes.data?.length === 0 && <Paragraph muted>{t("notes.none")}</Paragraph>}
      {notes.data && <Notes patientId={own.id} notes={notes.data} isDoctor={isDoctor} />}
    </Screen>
  );
}

/**
 * The steroid emergency card mark (Q36 ★): a treating doctor decides, shown the NHS 2020
 * threshold; the owner may mark it as their doctor told them. The app never infers it from
 * the medicines (rule 10). Whose mark it is stays visible.
 */
function SteroidCardSection({
  patientId,
  isDoctor,
  canMark,
}: {
  patientId: string;
  isDoctor: boolean;
  canMark: boolean;
}) {
  const t = useTranslations("app.clinician.steroid");
  const card = useCard();
  const errorText = useErrorText();
  const mark = useSteroidCard(patientId);
  const set = useMarkSteroidCard(patientId, isDoctor);
  const marked = mark.data ?? null;
  const ask = (on: boolean) =>
    Alert.alert(on ? t("markTitle") : t("clearTitle"), on ? t("markBody") : t("clearBody"), [
      { text: t("cancel"), style: "cancel" },
      {
        text: on ? t("mark") : t("clear"),
        style: on ? "default" : "destructive",
        onPress: () => set.mutate(on),
      },
    ]);
  return (
    <View style={card} testID="steroid-card">
      <Title>{t("title")}</Title>
      <Paragraph muted>{isDoctor ? t("threshold") : t("what")}</Paragraph>
      {mark.isPending && <LoadingView />}
      {mark.isError && (
        <RetryView text={errorText(mark.error)} onRetry={() => void mark.refetch()} />
      )}
      {mark.isSuccess && (
        <Paragraph>
          {marked
            ? t(
                !marked.by_doctor
                  ? "markedBySelf"
                  : marked.doctor_name
                    ? "markedByDoctor"
                    : "markedByFormerDoctor",
                {
                  date: formatDate(`${marked.marked_on}T12:00:00Z`),
                  name: marked.doctor_name ?? "",
                },
              )
            : t("none")}
        </Paragraph>
      )}
      {canMark && !isDoctor && !marked && <Paragraph muted>{t("ownerHint")}</Paragraph>}
      {canMark && mark.isSuccess && (
        <Button
          label={marked ? t("clear") : t("mark")}
          variant={marked ? "secondary" : "primary"}
          disabled={set.isPending}
          onPress={() => ask(!marked)}
        />
      )}
      {set.isError && <FormMessage kind="error" text={errorText(set.error)} />}
    </View>
  );
}

function useCard() {
  const p = usePalette();
  return [styles.card, { backgroundColor: p.surface, borderColor: p.border }];
}

/** Numbers only, with what they are counted from and what was left out (H15). */
function LevelCard({ patientId }: { patientId: string }) {
  const t = useTranslations("app.clinician.level");
  const errorText = useErrorText();
  const card = useCard();
  const [months, setMonths] = useState<(typeof MONTHS)[number]>("12");
  const stats = useLevelStats(patientId, "TAC", Number(months));
  return (
    <View style={card} testID="level-stats">
      <Title>{t("title")}</Title>
      <Paragraph muted>{t("what", { months: stats.data?.settle_months ?? 6 })}</Paragraph>
      <Segmented
        label={t("period")}
        options={MONTHS}
        value={months}
        labelOf={(m) => t("months", { n: Number(m) })}
        onSelect={setMonths}
        testID="level-months"
        showLabel
      />
      {stats.isPending && <LoadingView />}
      {stats.isError && (
        <RetryView text={errorText(stats.error)} onRetry={() => void stats.refetch()} />
      )}
      {stats.data && <LevelNumbers stats={stats.data} />}
      <Paragraph muted>{t("notAVerdict")}</Paragraph>
    </View>
  );
}

function LevelNumbers({ stats }: { stats: LevelStats }) {
  const t = useTranslations("app.clinician.level");
  const [listed, setListed] = useState(false);
  const unit = stats.unit ?? "";
  const leftOut = LEFT_OUT.filter((k) => stats[k] > 0);
  return (
    <>
      <Row label={t("n")} value={String(stats.n)} />
      {stats.reason ? (
        <Paragraph>{t(`reason.${stats.reason}`)}</Paragraph>
      ) : (
        <>
          {stats.mean && <Row label={t("mean")} value={`${stats.mean} ${unit}`} />}
          {stats.sd && <Row label={t("sd")} value={`${stats.sd} ${unit}`} />}
          {stats.cv_percent && <Row label={t("cv")} value={`${stats.cv_percent}%`} />}
          {stats.with_target > 0 && (
            <Row
              label={t("inTarget")}
              value={
                stats.in_target_percent
                  ? t("inTargetValue", {
                      n: stats.in_target,
                      of: stats.with_target,
                      pct: stats.in_target_percent,
                    })
                  : t("inTargetCount", { n: stats.in_target, of: stats.with_target })
              }
            />
          )}
        </>
      )}
      {/* the later of the period start and the first countable day (ISO dates compare as text) */}
      <Paragraph muted>
        {t("countedFrom", {
          date: formatDate(
            `${stats.counted_from && stats.counted_from > stats.since ? stats.counted_from : stats.since}T12:00:00Z`,
          ),
        })}
      </Paragraph>
      {leftOut.map((k) => (
        <Paragraph muted key={k}>
          {t(`leftOut.${k}`, { n: stats[k], months: stats.settle_months })}
        </Paragraph>
      ))}
      {/* values from different labs may come from different methods (Q63-6) */}
      {stats.labs.length > 1 && (
        <FormMessage kind="warning" text={t("labsMixed", { labs: stats.labs.join(", ") })} />
      )}
      {stats.lab_unknown > 0 && (
        <FormMessage kind="warning" text={t("labUnknown", { n: stats.lab_unknown })} />
      )}
      {/* the counted values themselves, so the doctor can check what went into the numbers */}
      {stats.values.length > 0 && (
        <Button
          variant="secondary"
          label={listed ? t("hideValues") : t("showValues", { n: stats.values.length })}
          onPress={() => setListed(!listed)}
        />
      )}
      {listed &&
        stats.values.map((v) => (
          <Row
            key={v.collected_on}
            label={
              v.lab
                ? `${formatDate(`${v.collected_on}T12:00:00Z`)} · ${v.lab}`
                : formatDate(`${v.collected_on}T12:00:00Z`)
            }
            value={`${v.value} ${unit}`}
          />
        ))}
    </>
  );
}

function Row({ label, value }: { label: string; value: string }) {
  const p = usePalette();
  return (
    <View style={styles.row} accessible accessibilityLabel={`${label}: ${value}`}>
      <Text style={[styles.rowLabel, { color: p.text }]}>{label}</Text>
      <Text style={[styles.rowValue, { color: p.text }]}>{value}</Text>
    </View>
  );
}

function TargetCard({
  target,
  name,
  patientId,
  canEnd,
}: {
  target: Target;
  name: string;
  patientId: string;
  canEnd: boolean;
}) {
  const t = useTranslations("app.clinician.targets");
  const tc = useTranslations("app.common");
  const p = usePalette();
  const errorText = useErrorText();
  const card = useCard();
  const end = useEndTarget(patientId);
  const range =
    target.low && target.high
      ? t("between", { low: target.low, high: target.high, unit: target.unit })
      : target.low
        ? t("atLeast", { low: target.low, unit: target.unit })
        : t("atMost", { high: target.high ?? "", unit: target.unit });
  const from = formatDate(`${target.valid_from}T12:00:00Z`);
  const today = dayOf(new Date());
  const current = target.valid_to === null || target.valid_to > today;
  return (
    <View style={card} testID={`target-${target.id}`}>
      <Text style={[styles.name, { color: p.text }]}>{name}</Text>
      <Paragraph>{range}</Paragraph>
      <Paragraph muted>
        {target.valid_to
          ? t("period", { from, to: formatDate(`${target.valid_to}T12:00:00Z`) })
          : t("since", { from })}
      </Paragraph>
      <Paragraph muted>{t("by", { name: target.set_by_name ?? t("formerDoctor") })}</Paragraph>
      {target.note && <Paragraph>{target.note}</Paragraph>}
      {canEnd && current && (
        <Button
          variant="secondary"
          label={t("end")}
          accessibilityLabel={t("endLabel", { name })}
          disabled={end.isPending}
          onPress={() =>
            Alert.alert(
              t("endLabel", { name }),
              t("endBody"),
              [
                { text: tc("cancel"), style: "cancel" },
                {
                  text: t("end"),
                  onPress: () => end.mutate({ target_id: target.id, on: today }),
                },
              ],
              { cancelable: true },
            )
          }
        />
      )}
      {end.isError && <FormMessage kind="error" text={errorText(end.error)} />}
    </View>
  );
}

/** A doctor sets a target for one test, from a day, in the catalog's unit. */
function TargetForm({ patientId }: { patientId: string }) {
  const t = useTranslations("app.clinician.targets.form");
  const tc = useTranslations("app.common");
  const errorText = useErrorText();
  const tests = useLabTests();
  const set = useSetTarget(patientId);
  const [search, setSearch] = useState("");
  const [code, setCode] = useState<string | null>(null);
  const [low, setLow] = useState("");
  const [high, setHigh] = useState("");
  const [from, setFrom] = useState(dayOf(new Date()));
  const [note, setNote] = useState("");
  const [saved, setSaved] = useState(false);
  const withUnit = (tests.data ?? []).filter((x) => x.canonical_unit);
  const q = search.trim().toLowerCase();
  const found = q
    ? withUnit
        .filter((x) => x.code.toLowerCase().includes(q) || x.name_mn.toLowerCase().includes(q))
        .slice(0, 6)
    : [];
  const chosen = withUnit.find((x) => x.code === code);
  const options = chosen && !found.includes(chosen) ? [chosen, ...found] : found;
  const num = (v: string) => (v.trim() === "" ? null : Number(v.trim().replace(",", ".")));
  const lo = num(low);
  const hi = num(high);
  const badNumber = Number.isNaN(lo) || Number.isNaN(hi);
  const badOrder = lo !== null && hi !== null && !badNumber && lo > hi;
  const valid = chosen !== undefined && (lo !== null || hi !== null) && !badNumber && !badOrder;
  const save = () =>
    Alert.alert(
      t("checkTitle"),
      t("checkBody", {
        name: chosen?.name_mn ?? "",
        low: low.trim() || "—",
        high: high.trim() || "—",
        unit: chosen?.canonical_unit ?? "",
        from: formatDate(`${from}T12:00:00Z`),
      }),
      [
        { text: tc("cancel"), style: "cancel" },
        {
          text: t("save"),
          onPress: () => {
            setSaved(false);
            set.mutate(
              { test_code: code ?? "", low, high, valid_from: from, note },
              {
                onSuccess: () => {
                  setSaved(true);
                  setLow("");
                  setHigh("");
                  setNote("");
                },
              },
            );
          },
        },
      ],
      { cancelable: true },
    );
  const nextYear = new Date();
  nextYear.setFullYear(nextYear.getFullYear() + 1);
  const yesterday = new Date();
  yesterday.setDate(yesterday.getDate() - 1);
  return (
    <View style={useCard()}>
      <Title>{t("title")}</Title>
      <TextField
        label={t("search")}
        value={search}
        onChangeText={setSearch}
        autoCapitalize="none"
        autoCorrect={false}
        testID="target-search"
      />
      {options.length > 0 && (
        <Choices
          label={t("test")}
          options={options.map((x) => x.code)}
          value={code}
          labelOf={(c) => {
            const x = withUnit.find((y) => y.code === c);
            return x ? `${x.name_mn} (${x.canonical_unit})` : c;
          }}
          onSelect={setCode}
        />
      )}
      <TextField
        label={t("low", { unit: chosen?.canonical_unit ?? "" })}
        value={low}
        onChangeText={setLow}
        keyboardType="decimal-pad"
        testID="target-low"
      />
      <TextField
        label={t("high", { unit: chosen?.canonical_unit ?? "" })}
        value={high}
        onChangeText={setHigh}
        keyboardType="decimal-pad"
        testID="target-high"
        error={badNumber ? t("number") : badOrder ? t("order") : undefined}
      />
      <PickerField
        label={t("from")}
        mode="date"
        value={from}
        onChange={setFrom}
        minimum={yesterday}
        maximum={nextYear}
      />
      <TextField
        label={t("note")}
        value={note}
        onChangeText={setNote}
        multiline
        maxLength={500}
        testID="target-note"
      />
      <Button
        label={t("save")}
        disabled={!valid || set.isPending}
        busy={set.isPending}
        onPress={save}
      />
      {saved && <FormMessage kind="success" text={t("saved")} />}
      {set.isError && <FormMessage kind="error" text={errorText(set.error)} />}
    </View>
  );
}

function Notes({
  patientId,
  notes,
  isDoctor,
}: {
  patientId: string;
  notes: {
    id: string;
    body: string;
    created_at: string;
    author_name: string | null;
    mine: boolean;
  }[];
  isDoctor: boolean;
}) {
  const t = useTranslations("app.clinician.notes");
  const tc = useTranslations("app.common");
  const errorText = useErrorText();
  const card = useCard();
  const add = useAddNote(patientId);
  const remove = useRemoveNote(patientId);
  const [body, setBody] = useState("");
  return (
    <>
      {notes.map((n) => (
        <View key={n.id} style={card} testID={`note-${n.id}`}>
          <Paragraph muted>
            {t("meta", {
              name: n.author_name ?? t("formerDoctor"),
              date: formatDateTime(n.created_at),
            })}
          </Paragraph>
          <Paragraph>{n.body}</Paragraph>
          {n.mine && (
            <Button
              variant="secondary"
              label={t("remove")}
              disabled={remove.isPending}
              onPress={() =>
                Alert.alert(
                  t("removeTitle"),
                  undefined,
                  [
                    { text: tc("cancel"), style: "cancel" },
                    { text: t("remove"), style: "destructive", onPress: () => remove.mutate(n.id) },
                  ],
                  { cancelable: true },
                )
              }
            />
          )}
        </View>
      ))}
      {remove.isError && <FormMessage kind="error" text={errorText(remove.error)} />}
      {isDoctor && (
        <>
          <TextField
            label={t("new")}
            value={body}
            onChangeText={setBody}
            multiline
            maxLength={2000}
            testID="note-body"
          />
          <Paragraph muted>{t("newHint")}</Paragraph>
          <Button
            label={t("add")}
            disabled={body.trim() === "" || add.isPending}
            busy={add.isPending}
            onPress={() => add.mutate(body, { onSuccess: () => setBody("") })}
          />
          {add.isError && <FormMessage kind="error" text={errorText(add.error)} />}
        </>
      )}
    </>
  );
}

const styles = StyleSheet.create({
  card: { borderWidth: 1, borderRadius: radius.md, padding: space.md, gap: space.sm },
  name: { fontSize: fontSize.body, fontWeight: "700" },
  row: { flexDirection: "row", justifyContent: "space-between", flexWrap: "wrap", gap: space.sm },
  rowLabel: { fontSize: fontSize.body },
  rowValue: { fontSize: fontSize.bodyLarge, fontWeight: "700", fontVariant: ["tabular-nums"] },
});
