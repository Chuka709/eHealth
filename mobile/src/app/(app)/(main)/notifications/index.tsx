import { useRouter } from "expo-router";
import { useTranslations } from "use-intl";

import { NavRow } from "@/components/nav-row";
import { Screen } from "@/components/screen";
import { LoadingView, RetryView } from "@/components/state-view";
import { Paragraph } from "@/components/text";
import { hasDetail, noticeKey } from "@/features/notices/notice-text";
import { type Notice, useMarkRead, useNotices } from "@/features/notices/use-notifications";
import { formatDateTime } from "@/lib/dates";
import { useErrorText } from "@/lib/use-error-text";

/** Notifications from the server (Phase 2.8f): the same notices a push announces, kept here. */
export default function NotificationsScreen() {
  const t = useTranslations("app.notifications");
  const router = useRouter();
  const errorText = useErrorText();
  const notices = useNotices();
  const markRead = useMarkRead();

  if (notices.isPending) return <LoadingView />;
  if (!notices.data) {
    return <RetryView text={errorText(notices.error)} onRetry={() => void notices.refetch()} />;
  }
  const open = (notice: Notice) => {
    if (notice.read_at === null) markRead.mutate(notice.id);
    if (hasDetail(notice)) router.push(`/notifications/${notice.id}` as never);
    else if (notice.kind === "share_invite") router.push("/caregivers/invitations" as never);
  };
  return (
    <Screen>
      {notices.data.length === 0 && <Paragraph muted>{t("empty")}</Paragraph>}
      {notices.data.map((notice) => (
        <NavRow
          key={notice.id}
          label={
            notice.read_at === null
              ? `${t("unread")} · ${t(noticeKey(notice))}`
              : t(noticeKey(notice))
          }
          hint={formatDateTime(notice.created_at)}
          onPress={() => open(notice)}
          a11yLabel={
            notice.read_at === null ? `${t("unreadSpoken")}. ${t(noticeKey(notice))}` : undefined
          }
          testID={`notice-${notice.id}`}
        />
      ))}
    </Screen>
  );
}
