import { getTranslations } from "next-intl/server";

import { Alert } from "@/components/ui";

import { NewUserForm } from "./new-user-form";

export default async function NewUserPage() {
  const t = await getTranslations("admin.new");
  return (
    <>
      <h1 className="text-2xl font-bold">{t("title")}</h1>
      <Alert tone="info">{t("hint")}</Alert>
      <NewUserForm />
    </>
  );
}
