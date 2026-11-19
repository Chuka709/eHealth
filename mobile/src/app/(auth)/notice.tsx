import { useRouter } from "expo-router";
import { useState } from "react";
import { useTranslations } from "use-intl";

import { Button } from "@/components/button";
import { FormMessage } from "@/components/form-message";
import { Screen } from "@/components/screen";
import { Paragraph, Title } from "@/components/text";
import { useNotice } from "@/features/auth/notice";
import { acknowledgeNotice } from "@/features/auth/session";
import { CallSupportButton } from "@/features/auth/support-contact";
import { formatDate } from "@/lib/dates";
import { supportPhone } from "@/lib/support";

/**
 * The notice that ended the session, shown until the user moves on (it survives a restart):
 * - adminReset: an admin reset the password (docs/04 §1 step 5a) — the victim of a fraudulent
 *   reset learns about it here and is told whom to call;
 * - reported: the user's own "Би хүсээгүй" locked the account;
 * - deleted: the deletion request was taken, with the date it becomes final.
 */
export default function NoticeScreen() {
  const t = useTranslations("app");
  const router = useRouter();
  const notice = useNotice();
  const [busy, setBusy] = useState(false);
  // An unreadable stored notice must not claim something that did not happen.
  const kind = notice?.kind ?? "none";

  const moveOn = (to: "/login" | "/welcome") => {
    setBusy(true);
    void acknowledgeNotice().then(() => router.replace(to));
  };
  const call = supportPhone ? { phone: supportPhone } : null;

  return (
    <Screen safeTop>
      {kind === "none" && (
        <>
          <Title>{t("noticeGeneric.title")}</Title>
          <Paragraph>{t("noticeGeneric.body")}</Paragraph>
        </>
      )}
      {kind === "adminReset" && (
        <>
          <Title>{t("adminReset.title")}</Title>
          <Paragraph>{t("adminReset.body")}</Paragraph>
          {/* Announced on open (FormMessage), so screen-reader users hear the call to action. */}
          <FormMessage
            kind="warning"
            text={call ? t("adminReset.ifNotYou", call) : t("adminReset.ifNotYouNoPhone")}
          />
        </>
      )}
      {kind === "reported" && (
        <>
          <Title>{t("reported.title")}</Title>
          <FormMessage
            kind="warning"
            text={call ? t("reported.body", call) : t("reported.bodyNoPhone")}
          />
        </>
      )}
      {notice?.kind === "deleted" && (
        <>
          <Title>{t("deleted.title")}</Title>
          <FormMessage
            kind="success"
            text={
              notice.scheduledFor
                ? t("deleted.body", { date: formatDate(notice.scheduledFor) })
                : t("deleted.bodyNoDate")
            }
          />
          <Paragraph>{t("deleted.undo")}</Paragraph>
        </>
      )}
      {kind !== "none" && (
        <CallSupportButton variant={kind === "deleted" ? "secondary" : "primary"} />
      )}
      <Button
        variant="secondary"
        label={
          kind === "adminReset" || kind === "none" ? t("adminReset.login") : t("common.understood")
        }
        busy={busy}
        onPress={() => moveOn(kind === "adminReset" || kind === "none" ? "/login" : "/welcome")}
      />
    </Screen>
  );
}
