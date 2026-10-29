import { getTranslations } from "next-intl/server";

import { Alert } from "@/components/ui";

import { ImportForm } from "./import-form";

export default async function ImportPage() {
  const t = await getTranslations("admin.import");
  return (
    <>
      <h1 className="text-2xl font-bold">{t("title")}</h1>
      <Alert tone="info">{t("hint")}</Alert>
      <ImportForm />
    </>
  );
}
