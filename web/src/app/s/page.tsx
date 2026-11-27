import { getTranslations } from "next-intl/server";

import { Card } from "@/components/ui";

import { PinForm } from "./pin-form";

/** A share link's landing page: the PIN, then the record (Phase 7.3). */
export default async function SharePage() {
  const t = await getTranslations("web.share");
  return (
    <main className="mx-auto flex w-full max-w-md flex-col gap-4 p-4">
      <h1 className="text-2xl font-semibold text-slate-900">{t("title")}</h1>
      <Card>
        <p className="text-slate-800">{t("intro")}</p>
        <PinForm />
      </Card>
    </main>
  );
}
