import type { Transplant, TransplantFields } from "./use-transplants";

export const ORGANS = [
  "kidney",
  "liver",
  "heart",
  "lung",
  "pancreas",
  "kidney_pancreas",
  "intestine",
  "cornea",
  "hsct",
  "other",
] as const;
export type Organ = (typeof ORGANS)[number];

export const DONOR_TYPES = [
  "living_related",
  "living_unrelated",
  "deceased_dbd",
  "deceased_dcd",
  "unknown",
] as const;
export type DonorType = (typeof DONOR_TYPES)[number];

// Where Mongolian patients are transplanted (docs/08); the API takes any ISO 3166 code.
export const COUNTRIES = [
  "MN",
  "KR",
  "IN",
  "CN",
  "TR",
  "RU",
  "JP",
  "DE",
  "US",
  "TH",
  "SG",
  "KZ",
] as const;
export type Country = (typeof COUNTRIES)[number];

export const BLOOD_TYPES = ["O+", "O-", "A+", "A-", "B+", "B-", "AB+", "AB-", "unknown"] as const;
export type BloodType = (typeof BLOOD_TYPES)[number];
export const SEROSTATUS = ["pos", "neg", "unknown"] as const;
export type Serostatus = (typeof SEROSTATUS)[number];

export type Precision = "day" | "month" | "year";

/** The earliest transplant date the API accepts (core/records: 1950). */
export const FIRST_YEAR = 1950;

export function yearInRange(year: number | null): boolean {
  return year !== null && year >= FIRST_YEAR && year <= new Date().getFullYear();
}

/** The form as the user fills it: text fields are strings ("" = not given). */
export type Draft = {
  organ: Organ | null;
  organDetail: string;
  precision: Precision;
  day: string | null; // YYYY-MM-DD (precision "day")
  year: number | null; // precision "month" / "year"
  month: number | null; // 1-12 (precision "month")
  country: Country | string;
  city: string;
  hospital: string;
  donorType: DonorType;
  donorRelation: string;
  recipientBloodType: BloodType | null;
  donorBloodType: BloodType | null;
  cmvDonor: Serostatus | null;
  cmvRecipient: Serostatus | null;
  hlaMismatch: string;
  inductionTherapy: string;
  primaryDisease: string;
  preTransplantDialysis: string;
  followUpCenter: string;
  followUpDoctor: string;
  notes: string;
  transplantNumber: number;
};

export function emptyDraft(transplantNumber = 1): Draft {
  return {
    organ: null,
    organDetail: "",
    precision: "day",
    day: null,
    year: null,
    month: null,
    country: "MN",
    city: "",
    hospital: "",
    donorType: "unknown",
    donorRelation: "",
    recipientBloodType: null,
    donorBloodType: null,
    cmvDonor: null,
    cmvRecipient: null,
    hlaMismatch: "",
    inductionTherapy: "",
    primaryDisease: "",
    preTransplantDialysis: "",
    followUpCenter: "",
    followUpDoctor: "",
    notes: "",
    transplantNumber,
  };
}

const text = (value: string | null | undefined) => value ?? "";

/** A stored record, back into the form (for editing). */
export function draftFrom(t: Transplant): Draft {
  const [y, m] = t.transplant_date.split("-").map(Number);
  const precision = t.date_precision as Precision;
  return {
    organ: t.organ as Organ,
    organDetail: text(t.organ_detail),
    precision,
    day: precision === "day" ? t.transplant_date : null,
    year: precision === "day" ? null : (y ?? null),
    month: precision === "month" ? (m ?? null) : null,
    country: t.country,
    city: text(t.city),
    hospital: t.hospital,
    donorType: t.donor_type as DonorType,
    donorRelation: text(t.donor_relation),
    recipientBloodType: (t.recipient_blood_type as BloodType | null) ?? null,
    donorBloodType: (t.donor_blood_type as BloodType | null) ?? null,
    cmvDonor: (t.cmv_donor as Serostatus | null) ?? null,
    cmvRecipient: (t.cmv_recipient as Serostatus | null) ?? null,
    hlaMismatch: text(t.hla_mismatch),
    inductionTherapy: text(t.induction_therapy),
    primaryDisease: text(t.primary_disease),
    preTransplantDialysis: text(t.pre_transplant_dialysis),
    followUpCenter: text(t.follow_up_center),
    followUpDoctor: text(t.follow_up_doctor),
    notes: text(t.notes),
    transplantNumber: t.transplant_number,
  };
}

const two = (n: number) => String(n).padStart(2, "0");

/** The date to send (YYYY-MM-DD); a month or year is sent as its first day (docs/03). */
export function draftDate(d: Draft): string | null {
  if (d.precision === "day") return d.day;
  if (!yearInRange(d.year)) return null;
  if (d.precision === "year") return `${d.year}-01-01`;
  return d.month === null ? null : `${d.year}-${two(d.month)}-01`;
}

export type Step = "organ" | "date" | "place" | "donor" | "extra";
export const STEPS: readonly Step[] = ["organ", "date", "place", "donor", "extra"];

/** What a step still needs before "Continue" (the required fields: organ, date, place). */
export function stepComplete(step: Step, d: Draft): boolean {
  switch (step) {
    case "organ":
      return d.organ !== null;
    case "date":
      return draftDate(d) !== null;
    case "place":
      return d.hospital.trim().length > 0 && /^[A-Z]{2}$/.test(d.country);
    default:
      return true;
  }
}

const optional = (value: string) => {
  const trimmed = value.trim();
  return trimmed.length > 0 ? trimmed : null;
};

/**
 * The request body; null while a required field is missing. When editing, `base` is the stored
 * record: fields this form does not show (surgeon, EBV, graft status ...) are kept as they are -
 * PUT replaces the whole record.
 */
export function toFields(d: Draft, base?: Transplant): TransplantFields | null {
  const date = draftDate(d);
  if (d.organ === null || date === null || !stepComplete("place", d)) return null;
  return {
    organ: d.organ,
    organ_detail: optional(d.organDetail),
    transplant_date: date,
    date_precision: d.precision,
    country: d.country,
    city: optional(d.city),
    hospital: d.hospital.trim(),
    surgeon: base?.surgeon ?? null,
    transplant_number: d.transplantNumber,
    donor_type: d.donorType,
    // a relation only for a living donor
    donor_relation: d.donorType.startsWith("living") ? optional(d.donorRelation) : null,
    recipient_blood_type: d.recipientBloodType,
    donor_blood_type: d.donorBloodType,
    abo_incompatible: base?.abo_incompatible ?? null,
    cmv_donor: d.cmvDonor,
    cmv_recipient: d.cmvRecipient,
    ebv_donor: (base?.ebv_donor as Serostatus | null | undefined) ?? null,
    ebv_recipient: (base?.ebv_recipient as Serostatus | null | undefined) ?? null,
    hla_mismatch: optional(d.hlaMismatch),
    primary_disease: optional(d.primaryDisease),
    pre_transplant_dialysis: optional(d.preTransplantDialysis),
    induction_therapy: optional(d.inductionTherapy),
    graft_status:
      (base?.graft_status as TransplantFields["graft_status"] | undefined) ?? "functioning",
    graft_status_date: base?.graft_status_date ?? null,
    graft_failure_reason: base?.graft_failure_reason ?? null,
    follow_up_center: optional(d.followUpCenter),
    follow_up_doctor: optional(d.followUpDoctor),
    notes: optional(d.notes),
  };
}
