/** A dose as the user entered it, as the app writes it (mobile `regimenText`): "08:00 · 2 мг,
 * 20:00 · 1,5 мг"; weekly with its days; as needed with its amount. Nothing is computed. */
export type DoseShape = {
  dose_amount?: string | null;
  dose_unit?: string | null;
  dose_unit_text?: string | null;
  schedule?: unknown;
};

type Translate = (key: string) => string;

export function doseText(t: Translate, regimen: DoseShape): string {
  const unitLabel = regimen.dose_unit
    ? regimen.dose_unit === "other"
      ? (regimen.dose_unit_text ?? "")
      : t(`units.${regimen.dose_unit}`)
    : "";
  const unit = unitLabel ? ` ${unitLabel}` : "";
  const schedule = (regimen.schedule ?? {}) as Record<string, unknown>;
  if (schedule.type === "prn") {
    return regimen.dose_amount ? `${t("prnHint")} · ${regimen.dose_amount}${unit}` : t("prnHint");
  }
  const times = Array.isArray(schedule.times)
    ? (schedule.times as { at?: unknown; amount?: unknown }[])
        .map((x) =>
          typeof x.amount === "string"
            ? `${String(x.at)} · ${x.amount}${unit}`
            : String(x.at ?? ""),
        )
        .join(", ")
    : "";
  if (schedule.type === "weekly" && Array.isArray(schedule.days)) {
    const days = (schedule.days as number[]).map((d) => t(`weekday.${d}`)).join(", ");
    return `${days}: ${times}`;
  }
  return times || t("noDose");
}
