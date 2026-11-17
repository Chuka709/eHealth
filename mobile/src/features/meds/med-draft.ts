import type { MedicationCreate, RegimenFields } from "./use-medications";

/**
 * The "add a medicine" / "change the dose" form. Input checks only - what the server would
 * refuse anyway (CLAUDE.md rule 6: no medical logic here, nothing suggested or judged).
 */

export const UNITS = [
  "mg",
  "mcg",
  "g",
  "ml",
  "iu",
  "unit",
  "tablet",
  "capsule",
  "drop",
  "puff",
  "sachet",
  "patch",
  "other",
] as const;
export type Unit = (typeof UNITS)[number];
export const WEEKDAYS = [1, 2, 3, 4, 5, 6, 7] as const;
export const MAX_TIMES = 12;

export type ScheduleKind = "daily" | "weekly" | "prn";
export type TimeRow = { key: string; at: string; amount: string };

export type ScheduleDraft = {
  kind: ScheduleKind;
  days: number[];
  times: TimeRow[];
  unit: Unit | null;
  unitText: string;
  prnAmount: string;
  instructions: string;
};

/** What a hand-typed medicine is, as the user says (Q34); "unknown" is sent as no answer. */
export const USER_CATEGORIES = ["immunosuppressant", "corticosteroid", "other", "unknown"] as const;
export type UserCategory = (typeof USER_CATEGORIES)[number];
export const sentCategory = (c: UserCategory | null) => (c === null || c === "unknown" ? null : c);

export type MedDraft = {
  catalogCode: string | null;
  userCategory: UserCategory | null;
  name: string;
  brand: string;
  form: string;
  strength: string;
  startedOn: string | null; // YYYY-MM-DD
  plannedEndOn: string | null;
  remindersEnabled: boolean;
  timezoneMode: "home" | "local";
  schedule: ScheduleDraft;
};

let rowSeq = 0;
export const timeRow = (at: string, amount = ""): TimeRow => {
  rowSeq += 1;
  return { key: `t${rowSeq}`, at, amount };
};

export const emptySchedule = (): ScheduleDraft => ({
  kind: "daily",
  days: [],
  times: [timeRow("08:00")],
  unit: null,
  unitText: "",
  prnAmount: "",
  instructions: "",
});

export const emptyMedDraft = (today: string): MedDraft => ({
  catalogCode: null,
  userCategory: null,
  name: "",
  brand: "",
  form: "",
  strength: "",
  startedOn: today,
  plannedEndOn: null,
  remindersEnabled: true,
  timezoneMode: "home",
  schedule: emptySchedule(),
});

// as the server: ASCII digits, 5 + 4, a decimal comma or point; "1,000" / "1.000" refused
const AMOUNT = /^[0-9]{1,5}([.,][0-9]{1,4})?$/;
const AMBIGUOUS = /^[1-9][0-9]{0,2}[.,][0-9]{3}$/;

export function amountOk(text: string): boolean {
  const value = text.trim();
  return AMOUNT.test(value) && !AMBIGUOUS.test(value) && Number(value.replace(",", ".")) > 0;
}

export type ScheduleErrors = Partial<
  Record<"times" | "duplicate" | "amountAll" | "unit" | "unitOther" | "days", true>
> & { amounts?: Record<string, true> };

export function scheduleErrors(s: ScheduleDraft): ScheduleErrors {
  const out: ScheduleErrors = {};
  const amounts: Record<string, true> = {};
  let withAmount = false;
  if (s.kind === "prn") {
    withAmount = s.prnAmount.trim() !== "";
    if (withAmount && !amountOk(s.prnAmount)) amounts.prn = true;
  } else {
    if (s.times.length === 0) out.times = true;
    if (new Set(s.times.map((r) => r.at)).size !== s.times.length) out.duplicate = true;
    const filled = s.times.filter((r) => r.amount.trim() !== "");
    if (filled.length > 0 && filled.length !== s.times.length) out.amountAll = true;
    withAmount = filled.length > 0;
    for (const r of filled) if (!amountOk(r.amount)) amounts[r.key] = true;
    if (s.kind === "weekly" && s.days.length === 0) out.days = true;
  }
  if (withAmount && s.unit === null) out.unit = true;
  if (s.unit === "other" && s.unitText.trim() === "") out.unitOther = true;
  if (Object.keys(amounts).length) out.amounts = amounts;
  return out;
}

export const hasErrors = (e: ScheduleErrors) => Object.keys(e).length > 0;

const optional = (text: string) => (text.trim() === "" ? null : text.trim());

export function regimenBody(
  s: ScheduleDraft,
  clientId: string,
  effectiveFrom: string,
  note?: string,
): RegimenFields {
  const withAmount =
    s.kind === "prn" ? s.prnAmount.trim() !== "" : s.times.some((r) => r.amount.trim() !== "");
  const schedule: Record<string, unknown> =
    s.kind === "prn"
      ? { type: "prn" }
      : {
          type: s.kind,
          times: s.times.map((r) =>
            withAmount ? { at: r.at, amount: r.amount.trim() } : { at: r.at },
          ),
          ...(s.kind === "weekly" ? { days: [...s.days].sort() } : {}),
        };
  return {
    client_id: clientId,
    effective_from: effectiveFrom,
    dose_amount: s.kind === "prn" && withAmount ? s.prnAmount.trim() : null,
    dose_unit: withAmount ? s.unit : null,
    dose_unit_text: withAmount && s.unit === "other" ? s.unitText.trim() : null,
    schedule,
    instructions: optional(s.instructions),
    changed_by_note: note ? optional(note) : null,
  };
}

export function createBody(
  d: MedDraft,
  clientId: string,
  regimenClientId: string,
  today: string,
): MedicationCreate {
  return {
    client_id: clientId,
    catalog_code: d.catalogCode,
    // only without a catalogue entry: the catalogue says what it is
    user_category: d.catalogCode ? null : sentCategory(d.userCategory),
    name: d.name.trim(),
    brand: optional(d.brand),
    form: optional(d.form),
    strength: optional(d.strength),
    route: "oral",
    is_long_term: d.plannedEndOn === null,
    started_on: d.startedOn,
    planned_end_on: d.plannedEndOn,
    reminders_enabled: d.remindersEnabled,
    reminder_timezone_mode: d.timezoneMode,
    regimen: regimenBody(d.schedule, regimenClientId, d.startedOn ?? today),
  };
}

/** A schedule as the form edits it (to start a dose change from the current one). */
export function draftFromSchedule(
  schedule: Record<string, unknown>,
  unit: string | null,
  unitText: string | null,
  doseAmount: string | null,
  instructions: string | null,
): ScheduleDraft {
  const kind: ScheduleKind =
    schedule.type === "weekly" ? "weekly" : schedule.type === "prn" ? "prn" : "daily";
  const times = Array.isArray(schedule.times)
    ? (schedule.times as { at?: unknown; amount?: unknown }[])
        .filter((t) => typeof t.at === "string")
        .map((t) => timeRow(String(t.at), typeof t.amount === "string" ? t.amount : ""))
    : [];
  return {
    kind,
    days: Array.isArray(schedule.days) ? (schedule.days as number[]) : [],
    times: kind === "prn" ? [timeRow("08:00")] : times,
    unit: (UNITS as readonly string[]).includes(unit ?? "") ? (unit as Unit) : null,
    unitText: unitText ?? "",
    prnAmount: doseAmount ?? "",
    instructions: instructions ?? "",
  };
}

/** "2 мг · 08:00, 1,5 мг · 20:00" - the schedule as written, for lists and history. */
export function scheduleText(
  schedule: Record<string, unknown>,
  unitLabel: string | null,
  prnLabel: string,
  doseAmount: string | null,
  weekday: (d: number) => string,
): string {
  const unit = unitLabel ? ` ${unitLabel}` : "";
  if (schedule.type === "prn") return doseAmount ? `${prnLabel} · ${doseAmount}${unit}` : prnLabel;
  const times = Array.isArray(schedule.times)
    ? (schedule.times as { at?: unknown; amount?: unknown }[])
        .map((t) =>
          typeof t.amount === "string" ? `${t.at} · ${t.amount}${unit}` : String(t.at ?? ""),
        )
        .join(", ")
    : "";
  if (schedule.type === "weekly" && Array.isArray(schedule.days)) {
    const days = (schedule.days as number[]).map(weekday).join(", ");
    return `${days}: ${times}`;
  }
  return times;
}
