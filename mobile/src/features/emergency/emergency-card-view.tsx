import { fontSize, radius, space } from "@labtrack/shared";
import { useState } from "react";
import { Linking, StyleSheet, View } from "react-native";
import { useLocale, useTranslations } from "use-intl";
import { Text } from "@/components/app-text";

import { Button } from "@/components/button";
import { FormMessage } from "@/components/form-message";
import { useRegimenText } from "@/features/meds/use-med-text";
import { elapsedText, transplantDateText } from "@/features/records/elapsed";
import { formatDate, formatDateTime } from "@/lib/dates";
import { usePalette } from "@/theme/use-palette";
import { graftKey, recentStopLines, steroidLines, transplantBloodLines } from "./card-text";
import type { EmergencyCard } from "./snapshot";

/** A number to dial: digits with an optional leading + (no pauses, codes or other characters);
 * null when nothing is left. */
export function dialable(phone: string): string | null {
  const digits = phone.replace(/[^0-9+]/g, "");
  const plus = digits.startsWith("+") ? "+" : "";
  const rest = digits.replace(/\+/g, "");
  return rest ? `${plus}${rest}` : null;
}

/** Where the card shown comes from: the server now; the saved copy because the server could
 * not be reached; or the saved copy by design (the locked app never asks the server). */
export type CardCopy = "live" | "offline" | "saved";

/**
 * The emergency card as an emergency team reads it (docs/08, H17): large text, nothing judged.
 * The order follows what a team needs first: who, allergies, medicines, blood type,
 * transplants, then whom to call. How current the card is shows at the top.
 * Every fact is shown as the server's card has it. The app adds no dose, range or advice
 * (CLAUDE.md rules 5, 10). An empty part is said to be "not recorded", never "none". Text
 * comes from the surrounding IntlProvider (the card's language). Used by the card screen and,
 * in 2.7c, by the locked app. It reads no API and opens no other screen; it can only place a
 * call.
 */
export function EmergencyCardView({ card, copy }: { card: EmergencyCard; copy: CardCopy }) {
  const t = useTranslations("app");
  const e = useTranslations("app.emergency");
  const tt = useTranslations("app.transplant");
  const lang = useLocale(); // read in the card's language by the screen reader
  const dose = useRegimenText();
  const p = usePalette();
  const [callFailed, setCallFailed] = useState<string | null>(null);

  const dated = (iso: string) => formatDate(`${iso}T12:00:00Z`); // a calendar date, not a moment
  const section = (title: string) => (
    <Text
      accessibilityRole="header"
      accessibilityLanguage={lang}
      style={[styles.section, { color: p.text }]}
    >
      {title}
    </Text>
  );
  const line = (text: string, muted = false) => (
    <Text
      accessibilityLanguage={lang}
      style={[styles.line, { color: muted ? p.textMuted : p.text }]}
    >
      {text}
    </Text>
  );
  const takesImmunosuppressant = card.dosed_medications.some(
    (m) => m.category === "immunosuppressant",
  );
  const when = formatDateTime(card.generated_at);

  return (
    <View style={styles.card}>
      {copy === "live" ? (
        line(e("updated", { when }), true)
      ) : (
        <FormMessage
          kind="warning"
          text={e(copy === "offline" ? "offline" : "saved", { when })}
          quiet
        />
      )}
      {(card.transplants.length > 0 || takesImmunosuppressant || card.steroid_card) && (
        // what a responder must see first: a panel with the emergency colour on its edge (2.12)
        <View
          style={[
            styles.leadPanel,
            { backgroundColor: p.surface, borderColor: p.border, borderLeftColor: p.emergency.bg },
          ]}
        >
          {card.transplants.length > 0 && (
            <Text accessibilityLanguage={lang} style={[styles.lead, { color: p.text }]}>
              {e("introTransplant")}
            </Text>
          )}
          {takesImmunosuppressant && (
            <Text accessibilityLanguage={lang} style={[styles.lead, { color: p.text }]}>
              {e("introImmunosuppressed")}
            </Text>
          )}
          {steroidLines(card, e as never).map((text, i) => (
            <Text
              key={text}
              accessibilityLanguage={lang}
              accessibilityRole={i === 0 ? "alert" : undefined}
              style={[
                i === 0 ? styles.lead : styles.line,
                { color: i === 2 ? p.textMuted : p.text },
              ]}
            >
              {text}
            </Text>
          ))}
        </View>
      )}

      <View style={[styles.box, { borderColor: p.border, backgroundColor: p.surface }]}>
        {line(`${e("name")}: ${card.patient.full_name}`)}
        {card.patient.birth_date && line(`${e("birthDate")}: ${dated(card.patient.birth_date)}`)}
      </View>

      {section(e("allergies"))}
      {/* none recorded is never "no allergies" (H17) */}
      {card.allergies.length === 0 &&
        line(
          card.no_known_allergies_on
            ? e("noKnownAllergy", { date: dated(card.no_known_allergies_on) })
            : e("noAllergy"),
        )}
      {keyed(card.allergies, (x) => x.substance).map(([k, a]) => (
        <View key={k}>
          {line(
            [
              a.substance,
              a.severity && a.severity !== "unknown"
                ? t(`health.allergy.severities.${a.severity}` as "health.allergy.severities.mild")
                : null,
              a.reaction,
            ]
              .filter(Boolean)
              .join(" — "),
          )}
        </View>
      ))}

      {section(e("meds"))}
      {card.dosed_medications.length === 0 ? line(e("noDosed")) : line(e("doseNote"), true)}
      {keyed(card.dosed_medications, (x) => `${x.name}${x.strength}`).map(([k, m]) => (
        <View key={k} style={[styles.box, { borderColor: p.border }]}>
          <Text accessibilityLanguage={lang} style={[styles.medName, { color: p.text }]}>
            {[m.name, m.brand, m.strength].filter(Boolean).join(" · ")}
          </Text>
          {line(e(`category.${m.category}`), true)}
          {line(m.dose ? dose(m.dose) : e("noDose"))}
          {keyed(m.upcoming_doses, (x) => x.effective_from).map(([k2, d]) => (
            <View key={k2}>
              {line(e("upcoming", { date: dated(d.effective_from), dose: dose(d) }))}
            </View>
          ))}
          {m.planned_end_on && line(e("endsOn", { date: dated(m.planned_end_on) }), true)}
        </View>
      ))}
      {card.other_medications.length > 0 &&
        line(
          `${e("otherMeds")}: ${card.other_medications
            .map((m) => (m.brand ? `${m.name} (${m.brand})` : m.name))
            .join(", ")}`,
        )}

      {recentStopLines(card, e as never).length > 0 && (
        <View style={[styles.box, { borderColor: p.border }]}>
          {line(e("recentlyStopped"), true)}
          {recentStopLines(card, e as never).map((text) => (
            <View key={text}>{line(text)}</View>
          ))}
        </View>
      )}

      {section(e("bloodType"))}
      {card.blood_type ? (
        <>
          {line(card.blood_type)}
          {line(e("bloodNote"), true)}
        </>
      ) : (
        line(
          card.blood_type_withheld === "conflict"
            ? e("bloodConflict")
            : card.blood_type_withheld === "hsct"
              ? e("bloodHsct")
              : e("notRecorded"),
        )
      )}

      {section(e("transplants"))}
      {card.transplants.length === 0 && line(e("notRecorded"))}
      {keyed(card.transplants, (x) => `${x.organ}${x.transplant_date}${x.transplant_number}`).map(
        ([k, tr]) => {
          const organ = t(`transplant.organ.${tr.organ}` as "transplant.organ.kidney");
          const since = elapsedText(tt, tr);
          return (
            <View key={k} style={[styles.box, { borderColor: p.border }]}>
              {line(
                [organ, tr.organ_detail, transplantDateText(tr), since].filter(Boolean).join(" · "),
              )}
              {tr.graft_status !== "functioning" &&
                line(
                  e("graftLabel", {
                    status: e(graftKey(tr) as "graft.failed"),
                  }),
                )}
              {transplantBloodLines(tr, e as never, card.blood_type_withheld).map((text) => (
                <View key={text}>{line(text)}</View>
              ))}
              {line([tr.hospital, tr.city, tr.country].filter(Boolean).join(", "), true)}
              {(tr.follow_up_center || tr.follow_up_doctor) &&
                line(
                  e("followUp", {
                    value: [tr.follow_up_center, tr.follow_up_doctor].filter(Boolean).join(", "),
                  }),
                  true,
                )}
            </View>
          );
        },
      )}

      {section(e("contacts"))}
      {card.contacts.length === 0 && line(e("notRecorded"))}
      {keyed(card.contacts, (x) => `${x.name}${x.phone}`).map(([k, c]) => {
        const number = dialable(c.phone);
        return (
          <View key={k} style={styles.contact}>
            {line(
              [
                c.name,
                c.is_transplant_center ? t("health.contact.centerMark") : c.relation,
                c.phone,
              ]
                .filter(Boolean)
                .join(" · "),
            )}
            {number && (
              <Button
                label={t("health.contact.call", { name: c.name })}
                variant="secondary"
                onPress={() => void Linking.openURL(`tel:${number}`).catch(() => setCallFailed(k))}
              />
            )}
            {/* said where the user is looking, under the button that failed */}
            {callFailed === k && (
              <FormMessage kind="error" text={t("health.contact.callFailed", { phone: c.phone })} />
            )}
          </View>
        );
      })}

      {line(e("disclaimer"), true)}
    </View>
  );
}

/** React keys from content: the card carries no row ids (they would link a copy back to the
 * records). Repeats get a counter, so every key is unique. */
function keyed<T>(items: readonly T[], base: (item: T) => string): [string, T][] {
  const seen = new Map<string, number>();
  return items.map((item) => {
    const k = base(item);
    const n = (seen.get(k) ?? 0) + 1;
    seen.set(k, n);
    return [`${k}#${n}`, item];
  });
}

const styles = StyleSheet.create({
  card: { gap: space.md },
  leadPanel: {
    gap: space.sm,
    padding: space.lg,
    borderRadius: radius.md,
    borderWidth: StyleSheet.hairlineWidth,
    borderLeftWidth: 6,
  },
  lead: { fontSize: fontSize.title, fontWeight: "700" },
  section: { fontSize: fontSize.title, fontWeight: "700", marginTop: space.sm },
  line: { fontSize: fontSize.bodyLarge, lineHeight: fontSize.bodyLarge * 1.4 },
  medName: { fontSize: fontSize.bodyLarge, fontWeight: "700" },
  box: {
    borderWidth: StyleSheet.hairlineWidth * 2,
    borderRadius: radius.md,
    padding: space.md,
    gap: space.xs,
  },
  contact: { gap: space.sm },
});
