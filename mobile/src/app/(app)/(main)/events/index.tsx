import { useTranslations } from "use-intl";

import { eventRow } from "@/features/health/forms";
import { RecordList } from "@/features/health/record-screens";
import { EVENTS } from "@/features/health/use-health";

export default function EventsScreen() {
  const t = useTranslations("app.health");
  return (
    <RecordList
      kind={EVENTS as never}
      route="/events"
      row={eventRow(t as (k: string) => string) as never}
      addLabel={t("event.new")}
    />
  );
}
