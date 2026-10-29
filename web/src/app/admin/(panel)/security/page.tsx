import Link from "next/link";
import { getFormatter, getTranslations } from "next-intl/server";

import { Alert } from "@/components/ui";
import { adminApi, failure } from "@/lib/server/api";

const KNOWN = new Set([
  "security.admin_token_self_use",
  "security.admin_network_activation",
  "security.user_report",
  "security.purge_failed",
]);

export default async function SecurityEventsPage() {
  const t = await getTranslations("admin");
  const tRoot = await getTranslations();
  const format = await getFormatter();
  const api = await adminApi();
  const { data, error, response } = await api.GET("/api/v1/admin/security-events", {
    params: { query: { limit: 100 } },
  });
  if (!data) {
    const problem = await failure(error, response.status);
    return <Alert tone="danger">{tRoot(`error.${problem.code}`)}</Alert>;
  }
  return (
    <>
      <h1 className="text-2xl font-bold">{t("security.title")}</h1>
      {data.length === 0 ? (
        <p>{t("security.empty")}</p>
      ) : (
        <div className="overflow-x-auto rounded-lg border border-slate-300 bg-white">
          <table className="w-full text-left text-sm">
            <thead className="bg-slate-100">
              <tr>
                <th scope="col" className="p-2">
                  {t("security.col.at")}
                </th>
                <th scope="col" className="p-2">
                  {t("security.col.event")}
                </th>
                <th scope="col" className="p-2">
                  {t("security.col.user")}
                </th>
              </tr>
            </thead>
            <tbody>
              {data.map((e) => (
                <tr key={e.id} className="border-t border-slate-200">
                  <td className="p-2 whitespace-nowrap">
                    {format.dateTime(new Date(e.at), { dateStyle: "medium", timeStyle: "short" })}
                  </td>
                  <td className="p-2">
                    <span aria-hidden="true">⚠ </span>
                    {KNOWN.has(e.action)
                      ? t(`event.${e.action}`)
                      : t("event.unknown", { action: e.action })}
                  </td>
                  <td className="p-2">
                    {e.target_user_id ? (
                      <Link
                        href={`/admin/users/${e.target_user_id}`}
                        className="text-blue-800 underline"
                      >
                        {e.target_user_id.slice(0, 8)}
                      </Link>
                    ) : (
                      "—"
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </>
  );
}
