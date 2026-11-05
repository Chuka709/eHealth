import { Host, Switch } from "@expo/ui";
import { StyleSheet } from "react-native";
import { useTranslations } from "use-intl";

import { Choices, MultiChoices, SelectList } from "@/components/choices";
import { dayOf, PickerField } from "@/components/date-field";
import { Paragraph } from "@/components/text";
import { TextField } from "@/components/text-field";
import { formatDate, formatDateTime } from "@/lib/dates";
import { RecordEditor, useOwnProfile } from "./record-screens";
import {
  ALLERGIES,
  type Allergy,
  APPOINTMENTS,
  type Appointment,
  CONTACTS,
  type Contact,
  EVENTS,
  type HealthEvent,
  QUESTIONS,
  type Question,
  useRecords,
} from "./use-health";

const opt = (text: string) => (text.trim() === "" ? null : text.trim());
const day = (iso: string) => formatDate(`${iso}T12:00:00Z`);
const PHONE = /^\+?[0-9][0-9 ()-]{3,22}[0-9]$/;

// --- clinical events ----------------------------------------------------------------------

const EVENT_KINDS = [
  "biopsy",
  "rejection",
  "infection",
  "hospitalization",
  "dialysis",
  "plasmapheresis",
  "ivig",
  "surgery",
  "procedure",
  "vaccination",
  "complication",
  "other",
] as const;
type EventDraft = {
  kind: (typeof EVENT_KINDS)[number] | null;
  title: string;
  startedOn: string | null;
  endedOn: string | null;
  place: string;
  description: string;
  outcome: string;
  transplantId: string | null;
};

export function EventEditor({ id }: { id: string }) {
  const t = useTranslations("app.health");
  return (
    <RecordEditor<HealthEvent, EventDraft>
      kind={EVENTS as never}
      id={id}
      titles={{ new: t("event.new"), edit: t("event.edit") }}
      nameOf={(e) => e.title}
      emptyDraft={() => ({
        kind: null,
        title: "",
        startedOn: null,
        endedOn: null,
        place: "",
        description: "",
        outcome: "",
        transplantId: null,
      })}
      toDraft={(e) => ({
        kind: e.kind as EventDraft["kind"],
        title: e.title,
        startedOn: e.started_on,
        endedOn: e.ended_on,
        place: e.place ?? "",
        description: e.description ?? "",
        outcome: e.outcome ?? "",
        transplantId: e.transplant_id,
      })}
      errorsOf={(d) => ({
        ...(d.kind ? {} : { kind: t("required") }),
        ...(d.title.trim() ? {} : { title: t("required") }),
        ...(d.startedOn ? {} : { startedOn: t("required") }),
      })}
      toBody={(d) => ({
        kind: d.kind,
        title: d.title.trim(),
        started_on: d.startedOn,
        ended_on: d.endedOn,
        place: opt(d.place),
        description: opt(d.description),
        outcome: opt(d.outcome),
        transplant_id: d.transplantId,
      })}
    >
      {({ draft, set, errors }) => (
        <>
          <SelectList
            label={t("event.kind")}
            options={EVENT_KINDS}
            value={draft.kind}
            labelOf={(k) => t(`event.kinds.${k}`)}
            onSelect={(kind) => set({ kind })}
            error={errors.kind}
          />
          <TextField
            label={t("event.title")}
            hint={t("event.titleHint")}
            value={draft.title}
            maxLength={200}
            error={errors.title}
            onChangeText={(title) => set({ title })}
          />
          <PickerField
            label={t("event.startedOn")}
            mode="date"
            value={draft.startedOn}
            maximum={new Date()}
            minimum={new Date(1950, 0, 1)}
            error={errors.startedOn}
            onChange={(startedOn) => set({ startedOn })}
          />
          <PickerField
            label={t("event.endedOn")}
            mode="date"
            value={draft.endedOn}
            maximum={new Date()}
            minimum={draft.startedOn ? new Date(`${draft.startedOn}T12:00:00`) : undefined}
            onChange={(endedOn) => set({ endedOn })}
          />
          <TextField
            label={t("event.place")}
            value={draft.place}
            maxLength={200}
            onChangeText={(place) => set({ place })}
          />
          <TextField
            label={t("event.description")}
            value={draft.description}
            maxLength={4000}
            multiline
            onChangeText={(description) => set({ description })}
          />
          <TextField
            label={t("event.outcome")}
            value={draft.outcome}
            maxLength={4000}
            multiline
            onChangeText={(outcome) => set({ outcome })}
          />
        </>
      )}
    </RecordEditor>
  );
}

export const eventRow = (t: (k: string) => string) => (e: HealthEvent) => ({
  label: e.title,
  hint: [t(`event.kinds.${e.kind}`), day(e.started_on)].join(" · "),
});

// --- allergies ----------------------------------------------------------------------------

const SEVERITIES = ["mild", "moderate", "severe", "unknown"] as const;
type AllergyDraft = {
  substance: string;
  reaction: string;
  severity: (typeof SEVERITIES)[number] | null;
  notedOn: string | null;
};

export function AllergyEditor({ id }: { id: string }) {
  const t = useTranslations("app.health");
  return (
    <RecordEditor<Allergy, AllergyDraft>
      kind={ALLERGIES as never}
      id={id}
      titles={{ new: t("allergy.new"), edit: t("allergy.edit") }}
      nameOf={(a) => a.substance}
      emptyDraft={() => ({ substance: "", reaction: "", severity: null, notedOn: null })}
      toDraft={(a) => ({
        substance: a.substance,
        reaction: a.reaction ?? "",
        severity: a.severity as AllergyDraft["severity"],
        notedOn: a.noted_on,
      })}
      errorsOf={(d): Record<string, string> =>
        d.substance.trim() ? {} : { substance: t("required") }
      }
      toBody={(d) => ({
        substance: d.substance.trim(),
        reaction: opt(d.reaction),
        severity: d.severity,
        noted_on: d.notedOn,
      })}
    >
      {({ draft, set, errors }) => (
        <>
          <TextField
            label={t("allergy.substance")}
            hint={t("allergy.substanceHint")}
            value={draft.substance}
            maxLength={200}
            error={errors.substance}
            onChangeText={(substance) => set({ substance })}
          />
          <TextField
            label={t("allergy.reaction")}
            value={draft.reaction}
            maxLength={200}
            onChangeText={(reaction) => set({ reaction })}
          />
          <Choices
            label={t("allergy.severity")}
            options={SEVERITIES}
            value={draft.severity}
            labelOf={(s) => t(`allergy.severities.${s}`)}
            onSelect={(severity) => set({ severity })}
            columns={2}
          />
          <PickerField
            label={t("allergy.notedOn")}
            mode="date"
            value={draft.notedOn}
            maximum={new Date()}
            minimum={new Date(1900, 0, 1)}
            onChange={(notedOn) => set({ notedOn })}
          />
        </>
      )}
    </RecordEditor>
  );
}

export const allergyRow = (t: (k: string) => string) => (a: Allergy) => ({
  label: a.substance,
  hint: [a.reaction, a.severity ? t(`allergy.severities.${a.severity}`) : null]
    .filter(Boolean)
    .join(" · "),
});

// --- emergency contacts -------------------------------------------------------------------

type ContactDraft = { name: string; relation: string; phone: string; center: boolean };

export function ContactEditor({ id }: { id: string }) {
  const t = useTranslations("app.health");
  return (
    <RecordEditor<Contact, ContactDraft>
      kind={CONTACTS as never}
      id={id}
      titles={{ new: t("contact.new"), edit: t("contact.edit") }}
      nameOf={(c) => c.name}
      emptyDraft={() => ({ name: "", relation: "", phone: "", center: false })}
      toDraft={(c) => ({
        name: c.name,
        relation: c.relation ?? "",
        phone: c.phone,
        center: c.is_transplant_center,
      })}
      errorsOf={(d) => ({
        ...(d.name.trim() ? {} : { name: t("required") }),
        ...(PHONE.test(d.phone.trim()) ? {} : { phone: t("contact.phoneInvalid") }),
      })}
      toBody={(d) => ({
        name: d.name.trim(),
        relation: opt(d.relation),
        phone: d.phone.trim(),
        is_transplant_center: d.center,
        sort_order: d.center ? 0 : 10,
      })}
    >
      {({ draft, set, errors }) => (
        <>
          <TextField
            label={t("contact.name")}
            value={draft.name}
            maxLength={200}
            error={errors.name}
            onChangeText={(name) => set({ name })}
          />
          <TextField
            label={t("contact.relation")}
            hint={t("contact.relationHint")}
            value={draft.relation}
            maxLength={200}
            onChangeText={(relation) => set({ relation })}
          />
          <TextField
            label={t("contact.phone")}
            hint={t("contact.phoneHint")}
            value={draft.phone}
            keyboardType="phone-pad"
            maxLength={24}
            error={errors.phone}
            onChangeText={(phone) => set({ phone })}
          />
          <Host matchContents={{ vertical: true }} style={styles.wide}>
            <Switch
              label={t("contact.center")}
              value={draft.center}
              onValueChange={(center) => set({ center })}
            />
          </Host>
        </>
      )}
    </RecordEditor>
  );
}

// --- appointments -------------------------------------------------------------------------

const APPOINTMENT_KINDS = ["lab", "clinic_visit", "biopsy", "imaging", "other"] as const;
const OFFSETS = [1440, 120, 60, 0] as const;
const STATUSES = ["planned", "done", "cancelled"] as const;
type AppointmentDraft = {
  kind: (typeof APPOINTMENT_KINDS)[number] | null;
  title: string;
  date: string | null;
  time: string | null;
  place: string;
  notes: string;
  offsets: number[];
  status: (typeof STATUSES)[number];
};

/** "YYYY-MM-DD" + "HH:MM" on the phone's clock -> an instant. */
function instantOf(date: string, time: string): string {
  const [y, m, d] = date.split("-").map(Number);
  const [h, min] = time.split(":").map(Number);
  return new Date(y, m - 1, d, h, min).toISOString();
}

const pad = (n: number) => String(n).padStart(2, "0");

export function AppointmentEditor({ id }: { id: string }) {
  const t = useTranslations("app.health");
  return (
    <RecordEditor<Appointment, AppointmentDraft>
      kind={APPOINTMENTS as never}
      id={id}
      titles={{ new: t("appointment.new"), edit: t("appointment.edit") }}
      nameOf={(a) => a.title}
      emptyDraft={() => ({
        kind: null,
        title: "",
        date: null,
        time: "09:00",
        place: "",
        notes: "",
        offsets: [1440, 120],
        status: "planned",
      })}
      toDraft={(a) => {
        const at = new Date(a.scheduled_at);
        return {
          kind: a.kind as AppointmentDraft["kind"],
          title: a.title,
          date: dayOf(at),
          time: `${pad(at.getHours())}:${pad(at.getMinutes())}`,
          place: a.place ?? "",
          notes: a.notes ?? "",
          offsets: a.reminder_offsets_min,
          status: a.status as AppointmentDraft["status"],
        };
      }}
      errorsOf={(d) => ({
        ...(d.kind ? {} : { kind: t("required") }),
        ...(d.title.trim() ? {} : { title: t("required") }),
        ...(d.date ? {} : { date: t("required") }),
        ...(d.time ? {} : { time: t("required") }),
      })}
      toBody={(d) => ({
        kind: d.kind,
        title: d.title.trim(),
        scheduled_at: instantOf(d.date ?? "", d.time ?? "09:00"),
        place: opt(d.place),
        notes: opt(d.notes),
        reminder_offsets_min: d.offsets,
        status: d.status,
      })}
    >
      {({ draft, set, errors }) => (
        <>
          <SelectList
            label={t("appointment.kind")}
            options={APPOINTMENT_KINDS}
            value={draft.kind}
            labelOf={(k) => t(`appointment.kinds.${k}`)}
            onSelect={(kind) => set({ kind })}
            error={errors.kind}
          />
          <TextField
            label={t("appointment.title")}
            hint={t("appointment.titleHint")}
            value={draft.title}
            maxLength={200}
            error={errors.title}
            onChangeText={(title) => set({ title })}
          />
          <PickerField
            label={t("appointment.date")}
            mode="date"
            value={draft.date}
            minimum={new Date(Date.now() - 5 * 365 * 86_400_000)}
            maximum={new Date(Date.now() + 2 * 365 * 86_400_000)}
            error={errors.date}
            onChange={(date) => set({ date })}
          />
          <PickerField
            label={t("appointment.time")}
            mode="time"
            value={draft.time}
            error={errors.time}
            onChange={(time) => set({ time })}
          />
          <TextField
            label={t("appointment.place")}
            value={draft.place}
            maxLength={200}
            onChangeText={(place) => set({ place })}
          />
          <TextField
            label={t("appointment.notes")}
            value={draft.notes}
            maxLength={4000}
            multiline
            onChangeText={(notes) => set({ notes })}
          />
          <Paragraph muted>{t("appointment.remindHint")}</Paragraph>
          <MultiChoices
            label={t("appointment.remind")}
            options={OFFSETS}
            values={draft.offsets}
            labelOf={(o) => t(`appointment.offsets.${o}`)}
            onToggle={(o) =>
              set({
                offsets: draft.offsets.includes(o)
                  ? draft.offsets.filter((x) => x !== o)
                  : [...draft.offsets, o].sort((a, b) => b - a),
              })
            }
          />
          <Choices
            label={t("appointment.status")}
            options={STATUSES}
            value={draft.status}
            labelOf={(s) => t(`appointment.statuses.${s}`)}
            onSelect={(status) => set({ status })}
          />
        </>
      )}
    </RecordEditor>
  );
}

export const appointmentRow = (t: (k: string) => string) => (a: Appointment) => ({
  label: a.title,
  hint: [
    formatDateTime(a.scheduled_at),
    t(`appointment.kinds.${a.kind}`),
    a.status === "planned" ? null : t(`appointment.statuses.${a.status}`),
  ]
    .filter(Boolean)
    .join(" · "),
});

// --- questions for the doctor -------------------------------------------------------------

const Q_STATUSES = ["open", "answered", "dropped"] as const;
type QuestionDraft = {
  text: string;
  answer: string;
  appointmentId: string | null;
  status: (typeof Q_STATUSES)[number];
};

export function QuestionEditor({ id }: { id: string }) {
  const t = useTranslations("app.health");
  const { own } = useOwnProfile();
  const appointments = useRecords(APPOINTMENTS as never, own?.id);
  const all = (appointments.data ?? []) as Appointment[];
  const now = Date.now();
  // coming planned ones - and always the one a question is already linked to (never dropped)
  const choosable = (linked: string | null) =>
    all.filter(
      (a) => a.id === linked || (a.status === "planned" && Date.parse(a.scheduled_at) >= now),
    );
  return (
    <RecordEditor<Question, QuestionDraft>
      kind={QUESTIONS as never}
      id={id}
      titles={{ new: t("question.new"), edit: t("question.edit") }}
      nameOf={(q) => (q.text.length > 40 ? `${q.text.slice(0, 40)}…` : q.text)}
      emptyDraft={() => ({ text: "", answer: "", appointmentId: null, status: "open" })}
      toDraft={(q) => ({
        text: q.text,
        answer: q.answer ?? "",
        appointmentId: q.appointment_id,
        status: q.status as QuestionDraft["status"],
      })}
      errorsOf={(d): Record<string, string> => (d.text.trim() ? {} : { text: t("required") })}
      toBody={(d) => ({
        text: d.text.trim(),
        answer: opt(d.answer),
        appointment_id: d.appointmentId,
        status: d.status,
      })}
    >
      {({ draft, set, errors }) => (
        <>
          <TextField
            label={t("question.text")}
            value={draft.text}
            maxLength={4000}
            multiline
            error={errors.text}
            onChangeText={(text) => set({ text })}
          />
          <SelectList
            label={t("question.appointment")}
            options={["", ...choosable(draft.appointmentId).map((a) => a.id)]}
            value={draft.appointmentId ?? ""}
            labelOf={(aid) => {
              const a = all.find((x) => x.id === aid);
              return a
                ? `${a.title} · ${formatDateTime(a.scheduled_at)}`
                : t("question.noAppointment");
            }}
            onSelect={(aid) => set({ appointmentId: aid === "" ? null : aid })}
          />
          <TextField
            label={t("question.answer")}
            value={draft.answer}
            maxLength={4000}
            multiline
            onChangeText={(answer) => set({ answer })}
          />
          <Choices
            label={t("question.status")}
            options={Q_STATUSES}
            value={draft.status}
            labelOf={(s) => t(`question.statuses.${s}`)}
            onSelect={(status) => set({ status })}
          />
        </>
      )}
    </RecordEditor>
  );
}

export const questionRow = (t: (k: string) => string) => (q: Question) => ({
  label: q.text.length > 80 ? `${q.text.slice(0, 80)}…` : q.text,
  hint: t(`question.statuses.${q.status}`),
});

const styles = StyleSheet.create({ wide: { alignSelf: "stretch" } });
