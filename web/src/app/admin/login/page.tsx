import { getTranslations } from "next-intl/server";

import { Alert } from "@/components/ui";

import { SignInForm } from "./sign-in-form";

export default async function SignInPage({ searchParams }: PageProps<"/admin/login">) {
  const t = await getTranslations("admin");
  const expired = (await searchParams).expired === "1";
  return (
    <main className="mx-auto flex w-full max-w-sm flex-col gap-4 p-6">
      <h1 className="text-2xl font-bold">{t("login.title")}</h1>
      {expired ? <Alert tone="warn">{t("login.expired")}</Alert> : null}
      <SignInForm />
    </main>
  );
}
