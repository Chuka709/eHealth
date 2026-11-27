import { useTranslations } from "use-intl";

import { appointmentRow } from "@/features/health/forms";
import { RecordList } from "@/features/health/record-screens";
import { APPOINTMENTS, type Appointment } from "@/features/health/use-health";

/** Coming ones first (soonest first), then the past (latest first). */
function order(items: Appointment[]): Appointment[] {
  const now = Date.now();
  const at = (a: Appointment) => Date.parse(a.scheduled_at);
  const coming = items.filter((a) => at(a) >= now).sort((a, b) => at(a) - at(b));
  const past = items.filter((a) => at(a) < now).sort((a, b) => at(b) - at(a));
  return [...coming, ...past];
}

export default function AppointmentsScreen() {
  const t = useTranslations("app.health");
  return (
    <RecordList<Appointment>
      kind={APPOINTMENTS as never}
      route="/appointments"
      row={appointmentRow(t as (k: string) => string)}
      addLabel={t("appointment.new")}
      sort={order}
    />
  );
}
