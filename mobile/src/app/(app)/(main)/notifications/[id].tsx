import { useLocalSearchParams, useRouter } from "expo-router";
import { useEffect, useState } from "react";
import { useTranslations } from "use-intl";

import { Screen } from "@/components/screen";
import { LoadingView, RetryView } from "@/components/state-view";
import { Paragraph, Title } from "@/components/text";
import { hasDetail, isResultNotice } from "@/features/notices/notice-text";
import { useDoseAlert, useMarkRead, useNotices } from "@/features/notices/use-notifications";
import { setActiveProfile } from "@/features/records/active-profile";
import { usePatients } from "@/features/records/use-profile";
import { formatDateTime } from "@/lib/dates";
import { useErrorText } from "@/lib/use-error-text";

/**
 * A dose alert (2.8e), opened from the list or a push: which profile and dose it was about,
 * and what is recorded for that dose *now* - a push already sent is not withdrawn when the dose
 * is recorded later (decision 3), so this screen says so instead. Never "not taken": only
 * whether something is recorded (decision (a)).
 */
export default function NoticeScreen() {
  const t = useTranslations("app.notifications");
  const errorText = useErrorText();
  const { id } = useLocalSearchParams<{ id: string }>();
  const noticeId = Number(id);
  const notices = useNotices();
  const notice = notices.data?.find((n) => n.id === noticeId);
  const detail = notice && hasDetail(notice) ? notice : undefined;
  const result = detail && isResultNotice(detail) ? detail : undefined;
  const dose = detail && !result ? detail : undefined;
  const alert = useDoseAlert(dose?.patient_id ?? null, dose ? Number(dose.entity_id) : null);
  const patients = usePatients();
  const markRead = useMarkRead();
  const unread = notice?.read_at === null;
  const mutateRead = markRead.mutate;

  useEffect(() => {
    if (unread) mutateRead(noticeId);
  }, [unread, noticeId, mutateRead]);

  // a result to review: on its own profile, in the review screen (5.5)
  const router = useRouter();
  const resultPatient = result?.patient_id ?? null;
  const resultId = result?.entity_id ?? null;
  useEffect(() => {
    if (resultPatient === null || resultId === null) return;
    setActiveProfile(resultPatient);
    router.replace(`/results/${resultId}`);
  }, [resultPatient, resultId, router]);

  // not in the list yet (a push newer than the last read): read it once more before "gone"
  const [checked, setChecked] = useState(false);
  const refetch = notices.refetch;
  const missing = notices.data !== undefined && notice === undefined;
  useEffect(() => {
    if (!missing || checked) return;
    void refetch().finally(() => setChecked(true));
  }, [missing, checked, refetch]);

  if (notices.isPending || (missing && !checked)) return <LoadingView />;
  if (!notices.data) {
    return <RetryView text={errorText(notices.error)} onRetry={() => void notices.refetch()} />;
  }
  // gone from the list: access ended, or not a notice of this account (a stale push)
  if (!detail) {
    return (
      <Screen>
        <Paragraph>{t("gone")}</Paragraph>
      </Screen>
    );
  }
  if (result) return <LoadingView />; // moving on to the review screen (effect above)
  if (alert.isPending) return <LoadingView />;
  if (!alert.data) {
    return <RetryView text={errorText(alert.error)} onRetry={() => void alert.refetch()} />;
  }
  const profile = patients.data?.find((p) => p.id === detail.patient_id);
  const state = alert.data.recorded ?? "none";
  return (
    <Screen>
      <Title>{t("dose.title")}</Title>
      <Paragraph>
        {profile ? t("dose.profile", { name: profile.full_name }) : t("dose.profileUnknown")}
      </Paragraph>
      <Paragraph>
        {t("dose.medication", {
          name: alert.data.medication_name,
          at: formatDateTime(alert.data.slot_at),
        })}
      </Paragraph>
      <Paragraph>{t(`dose.recorded.${state}`)}</Paragraph>
      <Paragraph muted>{t("dose.note")}</Paragraph>
    </Screen>
  );
}
