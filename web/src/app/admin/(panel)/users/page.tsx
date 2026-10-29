import Link from "next/link";
import { getTranslations } from "next-intl/server";

import { Alert, Button, Field, Input, Select } from "@/components/ui";
import { formatDate } from "@/lib/dates";
import { adminApi, failure } from "@/lib/server/api";

import { StatusBadge } from "./status-badge";

const STATUSES = ["pending_activation", "active", "locked", "disabled"] as const;
type Status = (typeof STATUSES)[number];

function one(value: string | string[] | undefined): string {
  return typeof value === "string" ? value : "";
}

export default async function UsersPage({ searchParams }: PageProps<"/admin/users">) {
  const tRoot = await getTranslations();
  const t = await getTranslations("admin");
  const params = await searchParams;
  const q = one(params.q).slice(0, 64);
  const status = (STATUSES as readonly string[]).includes(one(params.status))
    ? (one(params.status) as Status)
    : undefined;
  const pending = one(params.pending) === "1";
  const after = one(params.after).slice(0, 32);

  const api = await adminApi();
  const { data, error, response } = await api.GET("/api/v1/admin/users", {
    params: {
      query: {
        q: q || undefined,
        status,
        after: after || undefined,
        limit: 50,
        deletion_pending: pending,
      },
    },
  });
  const result = data ?? null;
  const problem = data ? null : await failure(error, response.status);

  const nextHref = result?.next_after
    ? `/admin/users?${new URLSearchParams({ q, status: status ?? "", pending: pending ? "1" : "", after: result.next_after })}`
    : null;

  return (
    <>
      <h1 className="text-2xl font-bold">{t("nav.users")}</h1>
      <nav className="flex gap-4" aria-label={t("users.status_filter")}>
        <Link
          href="/admin/users"
          aria-current={pending ? undefined : "page"}
          className="inline-flex min-h-11 items-center underline"
        >
          {t("users.all")}
        </Link>
        <Link
          href="/admin/users?pending=1"
          aria-current={pending ? "page" : undefined}
          className="inline-flex min-h-11 items-center underline"
        >
          {t("users.deletion_tab")}
        </Link>
      </nav>
      <form method="get" className="grid gap-3 sm:grid-cols-[1fr_14rem_auto] sm:items-end">
        {pending ? <input type="hidden" name="pending" value="1" /> : null}
        <Field label={t("users.search")} htmlFor="q">
          <Input id="q" name="q" defaultValue={q} maxLength={64} />
        </Field>
        <Field label={t("users.status_filter")} htmlFor="status">
          <Select id="status" name="status" defaultValue={status ?? ""}>
            <option value="">{t("users.all")}</option>
            {STATUSES.map((s) => (
              <option key={s} value={s}>
                {t(`status.${s}`)}
              </option>
            ))}
          </Select>
        </Field>
        <Button type="submit">{t("users.submit_search")}</Button>
      </form>

      {problem ? <Alert tone="danger">{tRoot(`error.${problem.code}`)}</Alert> : null}
      {result && result.items.length === 0 ? <p>{t("users.empty")}</p> : null}
      {result && result.items.length > 0 ? (
        <div className="overflow-x-auto rounded-lg border border-slate-300 bg-white">
          <table className="w-full text-left text-sm">
            <thead className="bg-slate-100">
              <tr>
                <th scope="col" className="p-2">
                  {t("users.col.username")}
                </th>
                <th scope="col" className="p-2">
                  {t("users.col.name")}
                </th>
                <th scope="col" className="p-2">
                  {t("users.col.role")}
                </th>
                <th scope="col" className="p-2">
                  {t("users.col.status")}
                </th>
                <th scope="col" className="p-2">
                  {t("users.col.phone")}
                </th>
                <th scope="col" className="p-2">
                  {pending ? t("users.col.deletion") : t("users.col.created")}
                </th>
              </tr>
            </thead>
            <tbody>
              {result.items.map((u) => (
                <tr key={u.id} className="border-t border-slate-200">
                  <td className="p-2">
                    <Link
                      href={`/admin/users/${u.id}`}
                      className="inline-flex min-h-11 items-center text-blue-800 underline"
                    >
                      {u.username}
                    </Link>
                  </td>
                  <td className="p-2">{u.display_name}</td>
                  <td className="p-2">{t(`role.${u.role}`)}</td>
                  <td className="p-2">
                    <StatusBadge
                      status={u.account_status}
                      deletionPending={!!u.deletion_scheduled_for}
                    />
                  </td>
                  <td className="p-2">
                    {u.phone_last4 ? (
                      <>
                        <span aria-hidden="true">••••{u.phone_last4}</span>
                        <span className="sr-only">
                          {t("detail.phone_last4", { last4: u.phone_last4 })}
                        </span>
                      </>
                    ) : (
                      "—"
                    )}
                  </td>
                  <td className="p-2">
                    {formatDate(
                      pending && u.deletion_scheduled_for ? u.deletion_scheduled_for : u.created_at,
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : null}
      {nextHref ? (
        <Link
          href={nextHref}
          className="inline-flex min-h-11 items-center self-start text-blue-800 underline"
        >
          {t("users.next_page")}
        </Link>
      ) : null}
    </>
  );
}
