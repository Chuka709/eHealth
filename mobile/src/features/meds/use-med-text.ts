import { useTranslations } from "use-intl";

import { scheduleText } from "./med-draft";
import type { Regimen } from "./use-medications";

/** What a dose text needs: a full regimen, or the emergency card's copy of one. */
export type DoseShape = Pick<Regimen, "dose_amount" | "dose_unit" | "dose_unit_text" | "schedule">;

type MedsT = (key: string) => string;

/** A regimen as words with a translator of `app.meds` (also outside React: the wallet PDF). */
export function regimenText(t: MedsT, regimen: DoseShape | null | undefined): string {
  if (!regimen) return t("noDose");
  const unit = regimen.dose_unit
    ? regimen.dose_unit === "other"
      ? regimen.dose_unit_text
      : t(`units.${regimen.dose_unit}`)
    : null;
  return scheduleText(regimen.schedule, unit, t("prnHint"), regimen.dose_amount, (d) =>
    t(`weekday.${d}`),
  );
}

/** A regimen as words: "08:00 · 2 мг, 20:00 · 1,5 мг" (the schedule as the user entered it). */
export function useRegimenText(): (regimen: DoseShape | null | undefined) => string {
  const t = useTranslations("app.meds");
  return (regimen) => regimenText(t as MedsT, regimen);
}
