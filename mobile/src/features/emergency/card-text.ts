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

const ABO = new Set(["O+", "O-", "A+", "A-", "B+", "B-", "AB+", "AB-"]);
type Tr = (key: string, values?: Record<string, string | number>) => string;
type CardTransplant = EmergencyCard["transplants"][number];

/**
 * For blood products (Q35, physician 2026-11-18): both ABO types, ABO-incompatible, CMV of the
 * donor and the recipient - each line only when recorded, never guessed.
 */
export function transplantBloodLines(
  tr: CardTransplant,
  e: Tr,
  withheld: EmergencyCard["blood_type_withheld"] = null,
): string[] {
  const lines: string[] = [];
  const known = (v: string | null) => (v && ABO.has(v) ? v : null);
  const recipient = known(tr.recipient_blood_type);
  const donor = known(tr.donor_blood_type);
  if (recipient || donor) {
    // after a stem-cell transplant, or with records that disagree, the recorded type is the
    // one before the transplant - never the current one (the card withholds that, H17)
    const before = tr.organ === "hsct" || withheld !== null;
    lines.push(
      e(before ? "transplantBloodBefore" : "transplantBlood", {
        recipient: recipient ?? e("unknownValue"),
        donor: donor ?? e("unknownValue"),
      }),
    );
  }
  if (tr.abo_incompatible) lines.push(e("aboIncompatible"));
  if (tr.cmv_donor || tr.cmv_recipient) {
    const sero = (v: string | null) => e(`sero.${v ?? "unknown"}`);
    lines.push(e("cmv", { donor: sero(tr.cmv_donor), recipient: sero(tr.cmv_recipient) }));
  }
  return lines;
}

/** A failed solid organ stays in the body (Q40); for a stem-cell or cornea graft it says less. */
export function graftKey(tr: CardTransplant): string {
  return tr.graft_status === "failed" && tr.organ !== "hsct" && tr.organ !== "cornea"
    ? "graft.failedInBody"
    : `graft.${tr.graft_status}`;
}

/**
 * The steroid emergency card (Q36): its title, the warning, then whose mark it is and when. An older
 * saved card has none.
 */
export function steroidLines(
  card: EmergencyCard,
  e: (key: string, values?: Record<string, string | number>) => string,
): string[] {
  const mark = card.steroid_card;
  if (!mark) return [];
  return [
    e("steroidCardTitle"),
    e("steroidCard"),
    e(mark.by_doctor ? "steroidCardByDoctor" : "steroidCardBySelf", {
      date: dated(mark.marked_on),
    }),
  ];
}

/**
 * The card's first line names what was transplanted (real phone 2026.11.27: "I have had a
 * transplant" left a first responder asking which organ): "Би бөөр, элэг шилжүүлэн
 * суулгуулсан." Each organ once, in the card's language; "other" alone keeps the general line.
 */
export function transplantIntro(transplants: readonly CardTransplant[], e: Tr): string {
  const kinds = new Set(transplants.map((tr) => tr.organ).filter((organ) => organ !== "other"));
  // a kidney-pancreas graft already names both (medical review L1)
  if (kinds.has("kidney_pancreas")) {
    kinds.delete("kidney");
    kinds.delete("pancreas");
  }
  // the card's own words, made for a sentence ("бөөр ба нойр булчирхай", "blood stem cell (bone
  // marrow)") - not the form's labels (medical review M1)
  const organs = [...kinds].map((organ) => e(`introOrgan.${organ}`));
  return organs.length > 0
    ? e("introTransplantOf", { organs: organs.join(", ") })
    : e("introTransplant");
}

/** Immunosuppressants stopped in the last 14 days, with the day (Q37); an older card has none. */
export function recentStopLines(card: EmergencyCard, e: Tr): string[] {
  return [...(card.recently_stopped ?? [])]
    .sort((a, b) => b.stopped_on.localeCompare(a.stopped_on)) // the latest stop first
    .map((m) =>
      e("recentStop", {
        name: m.brand ? `${m.name} (${m.brand})` : m.name,
        date: dated(m.stopped_on),
      }),
    );
}

/**
 * What a card made from this text carries beyond the medical core. `bloodDetails`: the
 * recipient's and the donor's ABO and CMV per transplant (Q35) - left off the wallpaper, which
 * anyone holding the phone sees without unlocking it (security review D5a).
 */
export type CardFields = { name: boolean; birthDate: boolean; bloodDetails?: boolean };

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
  if (card.transplants.length > 0) who.push(transplantIntro(card.transplants, e));
  if (card.dosed_medications.some((m) => m.category === "immunosuppressant")) {
    who.push(e("introImmunosuppressed"));
  }
  who.push(...steroidLines(card, e));
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
          lines.push(e("graftLabel", { status: e(graftKey(tr)) }));
        }
        if (fields.bloodDetails !== false) {
          lines.push(...transplantBloodLines(tr, e, card.blood_type_withheld));
        }
        lines.push([tr.hospital, tr.city, tr.country].filter(Boolean).join(", "));
        return lines;
      })
    : [e("notRecorded")];

  const medLines: string[] = card.dosed_medications.length ? [e("doseNote")] : [e("noDosed")];
  for (const m of card.dosed_medications) {
    const name = [m.name, m.brand].filter(Boolean).join(" · ");
    // the strength said as such, apart from the dose (UX audit #7)
    const strength = m.strength ? `; ${e("strength", { strength: m.strength })}` : "";
    medLines.push(
      `${name} (${e(`category.${m.category}`)}${strength}): ${m.dose ? regimenText(meds, m.dose) : e("noDose")}`,
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

  const stopped = recentStopLines(card, e);
  if (stopped.length) medLines.push(e("recentlyStopped"), ...stopped);

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
    : card.no_known_allergies_on
      ? [e("noKnownAllergy", { date: dated(card.no_known_allergies_on) })]
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
