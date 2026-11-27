import { fontSize, radius, space } from "@labtrack/shared";
import { StyleSheet, View } from "react-native";
import { useTranslations } from "use-intl";
import { Text } from "@/components/app-text";

import { usePalette } from "@/theme/use-palette";

import { useAdherence } from "./use-medications";

/** YYYY-MM of the Ulaanbaatar calendar (the server's summary month). */
export function ubMonth(now: Date): string {
  const parts = new Intl.DateTimeFormat("en-CA", {
    timeZone: "Asia/Ulaanbaatar",
    year: "numeric",
    month: "2-digit",
  }).formatToParts(now);
  const get = (type: string) => parts.find((x) => x.type === type)?.value ?? "";
  return `${get("year")}-${get("month")}`;
}

/**
 * This month's records as plain counts (Q23, H25): no colour, no threshold, no "good/bad",
 * never "missed" - "not recorded". Shown only when the server can answer (online).
 */
export function MonthSummary({ patientId, now }: { patientId: string; now: Date }) {
  const t = useTranslations("app.meds.summary");
  const p = usePalette();
  const query = useAdherence(patientId, ubMonth(now));
  const total = query.data?.total;
  if (!total) {
    return query.isError ? (
      <Text style={[styles.note, { color: p.textMuted }]}>{t("offline")}</Text>
    ) : null;
  }
  const lines =
    total.planned === 0
      ? [t("none")]
      : [
          total.percent_taken === null
            ? t("bodyNoPercent", { planned: total.planned, taken: total.taken })
            : t("body", {
                planned: total.planned,
                taken: total.taken,
                // the percent's own base (core/slots percent_taken): doses still open are out
                due: total.planned - total.open,
                percent: total.percent_taken,
              }),
          t("skipped", { n: total.skipped }),
          t("unrecorded", { n: total.unrecorded }),
          ...(total.open > 0 ? [t("open", { n: total.open })] : []),
        ];
  return (
    <View
      accessible
      style={[styles.box, { backgroundColor: p.surface, borderColor: p.border }]}
      testID="month-summary"
    >
      <Text accessibilityRole="header" style={[styles.title, { color: p.text }]}>
        {t("title")}
      </Text>
      {lines.map((line, i) => (
        // biome-ignore lint/suspicious/noArrayIndexKey: fixed lines, never reordered
        <Text key={i} style={[styles.body, { color: p.text }]}>
          {line}
        </Text>
      ))}
      <Text style={[styles.note, { color: p.textMuted }]}>{t("note")}</Text>
      {/* what the percent counts, said on the summary itself (Q27, ESPACOMP implementation) */}
      {total.percent_taken !== null && (
        <Text style={[styles.note, { color: p.textMuted }]}>{t("definition")}</Text>
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  box: {
    gap: space.xs,
    padding: space.md,
    borderRadius: radius.md,
    borderWidth: StyleSheet.hairlineWidth * 2,
  },
  title: { fontSize: fontSize.bodyLarge, fontWeight: "700" },
  body: { fontSize: fontSize.body, lineHeight: fontSize.body * 1.4 },
  note: { fontSize: fontSize.caption, lineHeight: fontSize.caption * 1.4 },
});
