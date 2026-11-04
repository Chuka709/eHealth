import { useTranslations } from "use-intl";

import { scheduleText } from "./med-draft";
import type { Regimen } from "./use-medications";

/** A regimen as words: "08:00 · 2 мг, 20:00 · 1,5 мг" (the schedule as the user entered it). */
export function useRegimenText(): (regimen: Regimen | null | undefined) => string {
  const t = useTranslations("app.meds");
  return (regimen) => {
    if (!regimen) return t("noDose");
    const unit = regimen.dose_unit
      ? regimen.dose_unit === "other"
        ? regimen.dose_unit_text
        : t(`units.${regimen.dose_unit}` as "units.mg")
      : null;
    return scheduleText(regimen.schedule, unit, t("prnHint"), regimen.dose_amount, (d) =>
      t(`weekday.${d}` as "weekday.1"),
    );
  };
}
