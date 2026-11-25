import type { components } from "@labtrack/shared";
import { flagGlyph } from "@labtrack/shared";
import { getTranslations } from "next-intl/server";

import { Alert, Badge, Button, Card, type Tone } from "@/components/ui";
import { formatDate, formatPartial } from "@/lib/dates";
import { doseText } from "@/lib/dose";
import { shareApi, shareSession } from "@/lib/server/share";

import { endShare } from "../actions";

type Lab = components["schemas"]["SharedLabOut"];

/** The server's flag only (rule 6): colour + glyph + text, never colour alone. */
function flagTone(flag: string | null | undefined): { tone: Tone; glyph: string } {
  if (flag === "critical_low" || flag === "critical_high") {
    return { tone: "danger", glyph: flagGlyph.critical };
  }
  if (flag === "low") return { tone: "info", glyph: flagGlyph.low };
  if (flag === "high") return { tone: "warn", glyph: flagGlyph.high };
  if (flag === "abnormal") return { tone: "warn", glyph: flagGlyph.abnormal };
  if (flag === "normal") return { tone: "ok", glyph: flagGlyph.normal };
  return { tone: "neutral", glyph: flagGlyph.no_reference };
}

const FLAGS = new Set([
  "normal",
  "low",
  "high",
  "critical_low",
  "critical_high",
  "abnormal",
  "no_reference",
]);

/** Read-only view of what the link shares (Phase 7.3). Nothing here computes or judges. */
export default async function ShareViewPage() {
  const t = await getTranslations("web.share");
  const tf = await getTranslations("app.upload.review.flags");
  const tr = await getTranslations("app.upload.review");
  const tl = await getTranslations();
  const tm = await getTranslations("app.meds");
  if (!(await shareSession())) return <Ended text={t("noSession")} title={t("endedTitle")} />;
  const api = await shareApi();
  const { data } = await api.GET("/api/v1/share/record");
  if (!data) return <Ended text={t("noSession")} title={t("endedTitle")} />;
  const label = (key: string, fallback: string) => (tl.has(key) ? tl(key) : fallback);
  const day = (iso: string | null | undefined) => (iso ? formatDate(iso) : "—");
  const SECTIONS = ["summary", "transplant", "meds", "labs", "events", "vitals"] as const;
  const notShared = SECTIONS.filter((k) => !data.scopes.includes(k));

  return (
    <main className="mx-auto flex w-full max-w-4xl flex-col gap-4 p-4">
      <header className="flex flex-col gap-2">
        <h1 className="text-2xl font-semibold text-slate-900">
          {t("recordOf", { name: data.full_name })}
        </h1>
        <p className="text-slate-700">
          {t("until", { time: formatDate(data.expires_at, true) })}
          {data.date_from || data.date_to
            ? ` · ${
                data.date_from && data.date_to
                  ? t("range", { from: day(data.date_from), to: day(data.date_to) })
                  : data.date_from
                    ? t("rangeFrom", { from: day(data.date_from) })
                    : t("rangeTo", { to: day(data.date_to) })
              }`
            : ""}
        </p>
        <Alert tone="info">{t("disclaimer")}</Alert>
        <form action={endShare}>
          <Button type="submit" variant="secondary">
            {t("end")}
          </Button>
        </form>
      </header>

      {data.summary ? (
        <Card title={t("sections.summary")}>
          <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-1">
            <dt className="text-slate-600">{t("birthDate")}</dt>
            <dd>{day(data.summary.birth_date)}</dd>
          </dl>
          <h3 className="font-semibold">{t("allergies")}</h3>
          {data.summary.allergies.length === 0 ? (
            <p className="text-slate-700">
              {/* a dated statement (Q39); none recorded is never "no allergies" (H17) */}
              {data.summary.no_known_allergies_on
                ? t("noKnownAllergies", { date: day(data.summary.no_known_allergies_on) })
                : t("noAllergies")}
            </p>
          ) : (
            <ul className="list-disc pl-5">
              {data.summary.allergies.map((a) => (
                <li key={a.substance}>
                  {[
                    a.substance,
                    a.reaction,
                    a.severity
                      ? label(`app.health.allergy.severities.${a.severity}`, a.severity)
                      : null,
                  ]
                    .filter(Boolean)
                    .join(" — ")}
                </li>
              ))}
            </ul>
          )}
        </Card>
      ) : null}

      {data.transplants ? (
        <Card title={t("sections.transplant")}>
          {data.transplants.length === 0 ? <p>{t("none")}</p> : null}
          {data.transplants.map((x) => (
            <dl
              key={`${x.organ}-${x.transplant_date}`}
              className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-1"
            >
              <dt className="text-slate-600">{t("organ")}</dt>
              <dd>{label(`app.transplant.organ.${x.organ}`, x.organ)}</dd>
              <dt className="text-slate-600">{t("date")}</dt>
              <dd>
                {x.transplant_date ? formatPartial(x.transplant_date, x.date_precision) : "—"}
              </dd>
              {(
                [
                  ["hospital", x.hospital],
                  [
                    "donor",
                    x.donor_type
                      ? label(`app.transplant.donor.${x.donor_type}`, x.donor_type)
                      : null,
                  ],
                  ["bloodTypes", pair(x.recipient_blood_type, x.donor_blood_type)],
                  ["cmv", pair(x.cmv_recipient, x.cmv_donor)],
                  ["ebv", pair(x.ebv_recipient, x.ebv_donor)],
                  ["primaryDisease", x.primary_disease],
                  ["induction", x.induction_therapy],
                  [
                    "graft",
                    x.graft_status
                      ? label(`app.emergency.graft.${x.graft_status}`, x.graft_status)
                      : null,
                  ],
                  ["followUp", [x.follow_up_center, x.follow_up_doctor].filter(Boolean).join(", ")],
                ] as const
              )
                .filter(([, v]) => v)
                .map(([k, v]) => (
                  <Row key={k} name={t(`transplantField.${k}`)} value={String(v)} />
                ))}
            </dl>
          ))}
        </Card>
      ) : null}

      {data.medications ? (
        <Card title={t("sections.meds")}>
          {data.medications.length === 0 ? <p>{t("none")}</p> : null}
          <ul className="flex flex-col gap-3">
            {data.medications.map((m) => (
              <li key={`${m.name}-${m.started_on}`} className="border-b border-slate-200 pb-2">
                <p className="font-semibold">
                  {[m.name, m.strength, m.form].filter(Boolean).join(" · ")}
                </p>
                <p className="text-sm text-slate-700">
                  {m.stopped_on
                    ? t("medDates", { from: day(m.started_on), to: day(m.stopped_on) })
                    : t("medSince", { from: day(m.started_on) })}
                </p>
                {m.regimens.map((g) => (
                  <p key={g.effective_from} className="text-sm">
                    {t("doseFrom", {
                      date: day(g.effective_from),
                      dose: doseText((k) => tm(k), g),
                    })}
                    {g.instructions ? ` — ${g.instructions}` : ""}
                  </p>
                ))}
              </li>
            ))}
          </ul>
        </Card>
      ) : null}

      {data.labs ? (
        <Card title={t("sections.labs")}>
          {data.labs.length === 0 ? (
            <p>{t("none")}</p>
          ) : (
            <LabTable labs={data.labs} t={t} tf={tf} tr={tr} />
          )}
        </Card>
      ) : null}

      {data.events ? (
        <Card title={t("sections.events")}>
          {data.events.length === 0 ? <p>{t("none")}</p> : null}
          <ul className="flex flex-col gap-2">
            {data.events.map((e) => (
              <li key={`${e.kind}-${e.started_on}-${e.title}`}>
                <span className="font-semibold">
                  {label(`app.health.event.kinds.${e.kind}`, e.kind)}
                </span>
                {e.title ? ` — ${e.title}` : ""} · {day(e.started_on)}
                {e.ended_on ? ` – ${day(e.ended_on)}` : ""}
                {e.place ? ` · ${e.place}` : ""}
                {e.outcome ? ` · ${e.outcome}` : ""}
              </li>
            ))}
          </ul>
        </Card>
      ) : null}

      {notShared.length > 0 ? (
        <p className="text-sm text-slate-700">
          {t("notShared", { sections: notShared.map((k) => t(`sections.${k}`)).join(", ") })}
        </p>
      ) : null}

      {data.vitals ? (
        <Card title={t("sections.vitals")}>
          {data.vitals.length === 0 ? (
            <p>{t("none")}</p>
          ) : (
            <table className="w-full text-left text-sm tabular-nums">
              <caption className="sr-only">{t("sections.vitals")}</caption>
              <thead>
                <tr>
                  <th scope="col" className="py-1">
                    {t("when")}
                  </th>
                  <th scope="col" className="py-1">
                    {t("measure")}
                  </th>
                  <th scope="col" className="py-1">
                    {t("value")}
                  </th>
                </tr>
              </thead>
              <tbody>
                {data.vitals.map((v) => (
                  <tr key={`${v.kind}-${v.measured_at}`} className="border-t border-slate-200">
                    <td className="py-1">{formatDate(v.measured_at, true)}</td>
                    <td className="py-1">{label(`app.health.vital.kinds.${v.kind}`, v.kind)}</td>
                    <td className="py-1">{[v.value, v.unit].filter(Boolean).join(" ")}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </Card>
      ) : null}
    </main>
  );
}

/** "recipient / donor", or nothing when neither is known (never a bare "/"). */
function pair(
  recipient: string | null | undefined,
  donor: string | null | undefined,
): string | null {
  if (!recipient && !donor) return null;
  return `${recipient ?? "—"} / ${donor ?? "—"}`;
}

function Row({ name, value }: { name: string; value: string }) {
  return (
    <>
      <dt className="text-slate-600">{name}</dt>
      <dd>{value}</dd>
    </>
  );
}

function LabTable({
  labs,
  t,
  tf,
  tr,
}: {
  labs: Lab[];
  t: Awaited<ReturnType<typeof getTranslations<"web.share">>>;
  tf: Awaited<ReturnType<typeof getTranslations<"app.upload.review.flags">>>;
  tr: Awaited<ReturnType<typeof getTranslations<"app.upload.review">>>;
}) {
  return (
    // a wide table scrolls sideways: the region takes focus so the keyboard can scroll it
    // biome-ignore lint/a11y/noNoninteractiveTabindex: a scrollable region must be focusable
    <section className="overflow-x-auto" tabIndex={0} aria-label={t("sections.labs")}>
      <table className="w-full min-w-[36rem] text-left text-sm tabular-nums">
        <caption className="sr-only">{t("sections.labs")}</caption>
        <thead>
          <tr>
            <th scope="col" className="py-1">
              {t("when")}
            </th>
            <th scope="col" className="py-1">
              {t("test")}
            </th>
            <th scope="col" className="py-1">
              {t("value")}
            </th>
            <th scope="col" className="py-1">
              {t("reference")}
            </th>
            <th scope="col" className="py-1">
              {t("flag")}
            </th>
          </tr>
        </thead>
        <tbody>
          {labs.map((r, i) => {
            const f = flagTone(r.flag);
            const flag = r.flag && FLAGS.has(r.flag) ? r.flag : "unknown";
            return (
              // biome-ignore lint/suspicious/noArrayIndexKey: rows have no id here (none is shared)
              <tr key={i} className="border-t border-slate-200 align-top">
                <td className="py-1">
                  {r.collected_precision === "day"
                    ? formatDate(r.collected_at)
                    : formatDate(r.collected_at, true)}
                  {r.collected_by_user ? (
                    <div className="text-slate-600">{tr("collectedByUser")}</div>
                  ) : null}
                  {r.lab_name ? <div className="text-slate-600">{r.lab_name}</div> : null}
                </td>
                <th scope="row" className="py-1 font-normal">
                  {r.test_name_mn ?? r.raw_name}
                </th>
                <td className="py-1">{[r.raw_value, r.raw_unit].filter(Boolean).join(" ")}</td>
                <td className="py-1">
                  {r.ref_text ?? "—"}
                  {r.critical_text ? (
                    <div className="text-slate-600">{t("critical", { text: r.critical_text })}</div>
                  ) : null}
                </td>
                <td className="py-1">
                  <Badge tone={f.tone} glyph={f.glyph}>
                    {tf(flag)}
                  </Badge>
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </section>
  );
}

function Ended({ title, text }: { title: string; text: string }) {
  return (
    <main className="mx-auto flex w-full max-w-md flex-col gap-4 p-4">
      <h1 className="text-2xl font-semibold text-slate-900">{title}</h1>
      <Card>
        <p className="text-slate-800">{text}</p>
      </Card>
    </main>
  );
}
