import { getTranslations } from "next-intl/server";

import { Button } from "@/components/ui";
import { adminApi, failure } from "@/lib/server/api";

import { signOut } from "../actions";
import { NavLinks } from "./nav-links";

export default async function PanelLayout({ children }: LayoutProps<"/admin">) {
  const t = await getTranslations("admin");
  const api = await adminApi();
  const { data: me, error, response } = await api.GET("/api/v1/admin/auth/me");
  if (!me) await failure(error, response.status);
  const isSuper = me?.role === "super_admin";
  const nav = [
    { href: "/admin/users", label: t("nav.users"), show: true },
    { href: "/admin/users/new", label: t("nav.new_user"), show: isSuper },
    { href: "/admin/import", label: t("nav.import"), show: isSuper },
    { href: "/admin/security", label: t("nav.security"), show: isSuper },
  ] as const;
  return (
    <>
      <a
        href="#main"
        className="sr-only focus:not-sr-only focus:absolute focus:left-2 focus:top-2 focus:z-10 focus:rounded focus:bg-white focus:p-2"
      >
        {t("nav.skip")}
      </a>
      <header className="border-b border-slate-300 bg-white print:hidden">
        <div className="mx-auto flex max-w-5xl flex-wrap items-center gap-4 p-3">
          <span className="font-bold">{t("title")}</span>
          <NavLinks
            label={t("nav.main")}
            items={nav.filter((item) => item.show).map(({ href, label }) => ({ href, label }))}
          />
          <span className="ml-auto text-sm text-slate-700">
            {t("nav.signed_in_as", { role: t(`role.${me?.role ?? "support"}`) })}
          </span>
          <form action={signOut}>
            <Button type="submit" variant="secondary">
              {t("nav.sign_out")}
            </Button>
          </form>
        </div>
      </header>
      <main
        id="main"
        tabIndex={-1}
        className="mx-auto flex w-full max-w-5xl flex-col gap-4 p-4 print:p-0"
      >
        {children}
      </main>
    </>
  );
}
