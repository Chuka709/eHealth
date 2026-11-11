import { useRouter } from "expo-router";
import { View } from "react-native";
import { useTranslations } from "use-intl";

import { Button } from "@/components/button";
import { FormMessage } from "@/components/form-message";
import { NavRow } from "@/components/nav-row";
import { Paragraph, Title } from "@/components/text";
import { APPOINTMENTS, type Appointment, useRecords } from "@/features/health/use-health";
import { TodayList } from "@/features/meds/today-list";
import { useTodayDoses } from "@/features/meds/use-today";
import { elapsedText, transplantDateText } from "@/features/records/elapsed";
import { useTransplants } from "@/features/records/use-transplants";
import { formatDateTime } from "@/lib/dates";
import { loading, OFFLINE_ERROR as OFFLINE } from "@/lib/query-state";
import { useErrorText } from "@/lib/use-error-text";

import { doseCounts, latestTransplant, nextAppointment, useHomeDoses } from "./home-data";

/** A section that could not load: says so and offers a retry, the rest of Home stays usable. */
function Failed({
  error,
  onRetry,
  section,
}: {
  error: unknown;
  onRetry: () => void;
  /** read with the retry, so each section's button is told apart */
  section: string;
}) {
  const t = useTranslations("status");
  const errorText = useErrorText();
  return (
    <>
      <FormMessage kind="error" text={errorText(error)} />
      <Button
        variant="link"
        label={t("retry")}
        accessibilityLabel={`${section}. ${t("retry")}`}
        onPress={onRetry}
      />
    </>
  );
}

function Loading() {
  const t = useTranslations("app.common");
  return (
    <View accessibilityLiveRegion="polite">
      <Paragraph muted>{t("loading")}</Paragraph>
    </View>
  );
}

/** The latest transplant: organ, date as given, time since (the server's count, never more). */
export function TransplantSection({ patientId }: { patientId: string }) {
  const t = useTranslations("app");
  const router = useRouter();
  const transplants = useTransplants(patientId);
  const list = transplants.data;
  const item = list ? latestTransplant(list) : undefined;
  return (
    <>
      <Title>{t("transplant.title")}</Title>
      {loading(transplants) ? (
        <Loading />
      ) : !list ? (
        <Failed
          section={t("transplant.title")}
          error={transplants.error ?? OFFLINE}
          onRetry={() => void transplants.refetch()}
        />
      ) : !item ? (
        <>
          <Paragraph>{t("transplant.empty")}</Paragraph>
          <Button label={t("transplant.add")} onPress={() => router.push("/transplants/new")} />
        </>
      ) : (
        <>
          <NavRow
            label={`${t(`transplant.organ.${item.organ}` as "transplant.title")} · ${transplantDateText(item)}`}
            hint={[
              elapsedText((k, v) => t(`transplant.${k}` as "transplant.title", v), item),
              item.hospital,
              item.graft_status === "failed" || item.graft_status === "removed"
                ? t("emergency.graftLabel", {
                    status: t(`emergency.graft.${item.graft_status}`),
                  })
                : null,
            ]
              .filter(Boolean)
              .join(" · ")}
            onPress={() => router.push({ pathname: "/transplants/[id]", params: { id: item.id } })}
            testID="home-transplant"
          />
          {list.length > 1 && (
            <Button
              variant="link"
              label={t("home.allTransplants", { count: list.length })}
              onPress={() => router.push("/transplants")}
            />
          )}
        </>
      )}
    </>
  );
}

/**
 * Today's doses Home offers to record (due ones and the next ones), each with one-tap
 * "Уусан" - the same list, queue and checks as the Эм tab, never a copy of its logic.
 */
export function TodaySection({ patientId, now }: { patientId: string; now: Date }) {
  const t = useTranslations("app");
  const router = useRouter();
  const { doses, meds, intakes, zones, waitingForZone } = useTodayDoses(patientId, now);
  const shown = useHomeDoses(doses, now.getTime());
  const { recorded, total } = doseCounts(doses);
  return (
    <>
      <Title>{t("meds.today")}</Title>
      {loading(meds) ||
      (!intakes.data && intakes.fetchStatus === "fetching") ||
      (!zones.data && zones.fetchStatus === "fetching") ? (
        <Loading />
      ) : !meds.data ? (
        <Failed
          section={t("meds.today")}
          error={meds.error ?? OFFLINE}
          onRetry={() => void meds.refetch()}
        />
      ) : total === 0 && waitingForZone.length === 0 ? (
        <Paragraph>{t("meds.todayEmpty")}</Paragraph>
      ) : (
        <>
          {total === 0 ? null : intakes.data ? (
            <Paragraph>{t("home.dosesRecorded", { recorded, total })}</Paragraph>
          ) : (
            // offline on a new day, or the server failed: no count that could be wrong, and
            // the doses stay recordable (the queue sends them later; a dose is one row - H20)
            <>
              <FormMessage kind="warning" text={t("home.dosesUnknown")} />
              <Button
                variant="link"
                label={t("home.retry")}
                accessibilityLabel={`${t("meds.today")}. ${t("home.retry")}`}
                onPress={() => void intakes.refetch()}
              />
            </>
          )}
          {shown.length > 0 || waitingForZone.length > 0 ? (
            <TodayList
              patientId={patientId}
              doses={shown}
              now={now.getTime()}
              waiting={waitingForZone}
            />
          ) : (
            <Paragraph>{t("home.dosesAllRecorded")}</Paragraph>
          )}
        </>
      )}
      <Button variant="link" label={t("home.allMeds")} onPress={() => router.push("/meds")} />
    </>
  );
}

/** The next planned appointment, in Ulaanbaatar time like everywhere in the app. */
export function AppointmentSection({ patientId, now }: { patientId: string; now: Date }) {
  const t = useTranslations("app");
  const router = useRouter();
  const appointments = useRecords(APPOINTMENTS as never, patientId);
  const list = appointments.data as Appointment[] | undefined;
  const next = list ? nextAppointment(list, now) : undefined;
  return (
    <>
      <Title>{t("home.nextAppointment")}</Title>
      {loading(appointments) ? (
        <Loading />
      ) : !list ? (
        <Failed
          section={t("home.nextAppointment")}
          error={appointments.error ?? OFFLINE}
          onRetry={() => void appointments.refetch()}
        />
      ) : next ? (
        <NavRow
          label={next.title}
          hint={[
            formatDateTime(next.scheduled_at),
            t(`health.appointment.kinds.${next.kind}` as "home.allMeds"),
            next.place,
          ]
            .filter(Boolean)
            .join(" · ")}
          onPress={() => router.push({ pathname: "/appointments/[id]", params: { id: next.id } })}
          testID="home-appointment"
        />
      ) : (
        <Paragraph>{t("home.noAppointment")}</Paragraph>
      )}
      <Button
        variant="link"
        label={t("home.allAppointments")}
        onPress={() => router.push("/appointments")}
      />
    </>
  );
}
