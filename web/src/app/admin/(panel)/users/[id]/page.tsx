import Link from "next/link";
import { notFound } from "next/navigation";
import { getFormatter, getTranslations } from "next-intl/server";

import { Alert, Card } from "@/components/ui";
import { adminApi, failure } from "@/lib/server/api";

import { StatusBadge } from "../status-badge";
import {
  CancelDeletionPanel,
  ClearLockoutPanel,
  EnrolIdentityPanel,
  IssueTokenPanel,
  RevealPhonePanel,
  StatusPanel,
} from "./panels";

const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

export default async function UserDetailPage({ params }: PageProps<"/admin/users/[id]">) {
  const { id } = await params;
  if (!UUID.test(id)) notFound();
  const t = await getTranslations("admin");
  const format = await getFormatter();
  const api = await adminApi();
  const [{ data: user, error, response }, { data: me }] = await Promise.all([
    api.GET("/api/v1/admin/users/{user_id}", { params: { path: { user_id: id } } }),
    api.GET("/api/v1/admin/auth/me"),
  ]);
  if (!user) {
    const problem = await failure(error, response.status);
    if (problem.code === "admin.user_not_found") notFound();
    return <Alert tone="danger">{(await getTranslations())(`error.${problem.code}`)}</Alert>;
  }
  const isSuper = me?.role === "super_admin";
  const deleting = !!user.deletion_scheduled_for;
  const when = (iso: string) =>
    format.dateTime(new Date(iso), { dateStyle: "medium", timeStyle: "short" });

  return (
    <>
      <Link href="/admin/users" className="self-start py-2 text-blue-800 underline">
        {t("detail.back")}
      </Link>
      <header className="flex flex-wrap items-center gap-3">
        <h1 className="text-2xl font-bold">{user.display_name}</h1>
        <span className="text-slate-700">@{user.username}</span>
        <span>{t(`role.${user.role}`)}</span>
        <StatusBadge status={user.account_status} deletionPending={deleting} />
      </header>
      <ul className="flex flex-col gap-1 text-slate-800">
        <li>
          {user.phone_last4
            ? t("detail.phone_last4", { last4: user.phone_last4 })
            : t("detail.no_phone")}
        </li>
        <li>{t("detail.sessions", { count: user.active_sessions })}</li>
        <li>{t("detail.checks_today", { count: user.identity_checks_today })}</li>
        {user.live_token ? (
          <li>
            {t("detail.live_token", {
              purpose: t(`purpose.${user.live_token.purpose}`),
              channel: t(`channel.${user.live_token.channel}`),
              expires: when(user.live_token.expires_at),
            })}
          </li>
        ) : null}
      </ul>

      {deleting && user.deletion_scheduled_for ? (
        <>
          <Alert tone="warn">
            {t("detail.deletion", {
              date: format.dateTime(new Date(user.deletion_scheduled_for), { dateStyle: "long" }),
            })}
          </Alert>
          {isSuper ? <CancelDeletionPanel userId={user.id} /> : null}
        </>
      ) : (
        <div className="grid gap-4 md:grid-cols-2">
          {isSuper && user.account_status === "pending_activation" ? (
            <Card title={t("activation.title")} className="md:col-span-2">
              <p>{t("activation.hint")}</p>
              <IssueTokenPanel
                userId={user.id}
                purpose="activation"
                hasPhone={!!user.phone_last4}
              />
              <Link
                href={`/admin/users/${user.id}/card`}
                className="self-start py-2 text-blue-800 underline"
              >
                {t("card.print")}
              </Link>
            </Card>
          ) : null}
          {isSuper &&
          user.account_status !== "pending_activation" &&
          user.account_status !== "disabled" ? (
            <Card title={t("reset.title")} className="md:col-span-2">
              <p>{t("identity.hint")}</p>
              <IssueTokenPanel
                userId={user.id}
                purpose="admin_reset"
                hasPhone={!!user.phone_last4}
              />
            </Card>
          ) : null}
          <Card title={t("phone.title")}>
            <RevealPhonePanel userId={user.id} />
          </Card>
          <Card title={t("unlock.title")}>
            <p>{t("unlock.hint")}</p>
            <ClearLockoutPanel userId={user.id} />
          </Card>
          {user.account_status !== "pending_activation" ? (
            <Card title={t("status_change.title")}>
              <StatusPanel userId={user.id} current={user.account_status} isSuper={isSuper} />
            </Card>
          ) : null}
          {isSuper ? (
            <Card title={t("identity.enrol_title")}>
              <EnrolIdentityPanel userId={user.id} />
            </Card>
          ) : null}
        </div>
      )}
    </>
  );
}
