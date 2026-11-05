import { useTranslations } from "use-intl";

import { allergyRow } from "@/features/health/forms";
import { RecordList } from "@/features/health/record-screens";
import { ALLERGIES } from "@/features/health/use-health";

export default function AllergiesScreen() {
  const t = useTranslations("app.health");
  return (
    <RecordList
      kind={ALLERGIES as never}
      route="/allergies"
      row={allergyRow(t as (k: string) => string) as never}
      addLabel={t("allergy.new")}
    />
  );
}
