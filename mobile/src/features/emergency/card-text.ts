import en from "@labtrack/shared/messages/en.json";
import mn from "@labtrack/shared/messages/mn.json";
import { createTranslator } from "use-intl";

import { regimenText } from "@/features/meds/use-med-text";
import { elapsedText, transplantDateText } from "@/features/records/elapsed";
import { formatDate, formatDateTime } from "@/lib/dates";
import type { Locale } from "@/lib/i18n";

import type { EmergencyCard } from "./snapshot";

/**
 * The card as plain lines in one language, for what leaves the app: the wallet card (PDF), the
 * lock-screen wallpaper and the Medical ID text. Same facts, order and wording as the card
 * screen (H17): "not recorded" never reads as "none", doses as recorded with their note, a
 * withheld blood type with its reason. Built without React, in either language whatever the
 * app's language is.
 */

export type CardSection = { heading?: string; lines: string[] };
export type CardText = {
  title: string;
  /** the lines a team reads first: who, transplant, blood type */
  front: CardSection[];
  /** medicines, allergies, whom to call, and the card's date and limits */
  back: CardSection[];
};

const messages = { mn, en } as const;
type T = (key: string, values?: Record<string, string | number>) => string;

export function translatorFor(locale: Locale) {
  const tr = createTranslator({ locale, messages: messages[locale] });
  // keys are built from the card's enums: checked by the screen's typed use; here as strings
  return ((key: string, values?: Record<string, string | number>) =>
    tr(key as never, values as never)) as T;
}

const dated = (iso: string) => formatDate(`${iso}T12:00:00Z`);

export type CardFields = { name: boolean; birthDate: boolean };

export function cardText(
  card: EmergencyCard,
  locale: Locale,
  fields: CardFields = { name: true, birthDate: true },
): CardText {
  const t = translatorFor(locale);
  const e = (key: string, values?: Record<string, string | number>) =>
    t(`app.emergency.${key}`, values);
  const meds = (key: string) => t(`app.meds.${key}`);
  const tt = (key: string, values?: Record<string, string | number>) =>
    t(`app.transplant.${key}`, values);

  const who: string[] = [];
  if (card.transplants.length > 0) who.push(e("introTransplant"));
  if (card.dosed_medications.some((m) => m.category === "immunosuppressant")) {
    who.push(e("introImmunosuppressed"));
  }
  if (fields.name) who.push(`${e("name")}: ${card.patient.full_name}`);
  if (fields.birthDate && card.patient.birth_date) {
    who.push(`${e("birthDate")}: ${dated(card.patient.birth_date)}`);
  }

  const blood = card.blood_type
    ? [card.blood_type, e("bloodNote")]
    : [
        card.blood_type_withheld === "conflict"
          ? e("bloodConflict")
          : card.blood_type_withheld === "hsct"
            ? e("bloodHsct")
            : e("notRecorded"),
      ];

  const transplants = card.transplants.length
    ? card.transplants.flatMap((tr) => {
        const organ = t(`app.transplant.organ.${tr.organ}`);
        const since = elapsedText(tt, tr);
        const lines = [
          [organ, tr.organ_detail, transplantDateText(tr), since].filter(Boolean).join(" · "),
        ];
        if (tr.graft_status !== "functioning") {
          lines.push(e("graftLabel", { status: e(`graft.${tr.graft_status}`) }));
        }
        lines.push([tr.hospital, tr.city, tr.country].filter(Boolean).join(", "));
        return lines;
      })
    : [e("notRecorded")];

  const medLines: string[] = card.dosed_medications.length ? [e("doseNote")] : [e("noDosed")];
  for (const m of card.dosed_medications) {
    const name = [m.name, m.brand, m.strength].filter(Boolean).join(" · ");
    medLines.push(
      `${name} (${e(`category.${m.category}`)}): ${m.dose ? regimenText(meds, m.dose) : e("noDose")}`,
    );
    for (const d of m.upcoming_doses) {
      medLines.push(e("upcoming", { date: dated(d.effective_from), dose: regimenText(meds, d) }));
    }
    if (m.planned_end_on) medLines.push(e("endsOn", { date: dated(m.planned_end_on) }));
  }
  if (card.other_medications.length) {
    medLines.push(
      `${e("otherMeds")}: ${card.other_medications
        .map((m) => (m.brand ? `${m.name} (${m.brand})` : m.name))
        .join(", ")}`,
    );
  }

  const allergies = card.allergies.length
    ? card.allergies.map((a) =>
        [
          a.substance,
          a.severity && a.severity !== "unknown"
            ? t(`app.health.allergy.severities.${a.severity}`)
            : null,
          a.reaction,
        ]
          .filter(Boolean)
          .join(" — "),
      )
    : [e("noAllergy")];

  const contacts = card.contacts.length
    ? card.contacts.map((c) =>
        [c.name, c.is_transplant_center ? t("app.health.contact.centerMark") : c.relation, c.phone]
          .filter(Boolean)
          .join(" · "),
      )
    : [e("notRecorded")];

  return {
    title: e("title"),
    front: [
      { lines: who },
      { heading: e("bloodType"), lines: blood },
      { heading: e("transplants"), lines: transplants },
    ],
    back: [
      { heading: e("allergies"), lines: allergies },
      { heading: e("meds"), lines: medLines },
      { heading: e("contacts"), lines: contacts },
      {
        lines: [e("updated", { when: formatDateTime(card.generated_at) }), e("disclaimer")],
      },
    ],
  };
}
