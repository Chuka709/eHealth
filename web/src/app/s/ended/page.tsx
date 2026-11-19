import { getTranslations } from "next-intl/server";

import { Card } from "@/components/ui";

export default async function ShareEndedPage() {
  const t = await getTranslations("web.share");
  return (
    <main className="mx-auto flex w-full max-w-md flex-col gap-4 p-4">
      <h1 className="text-2xl font-semibold text-slate-900">{t("endedTitle")}</h1>
      <Card>
        <p className="text-slate-800">{t("ended")}</p>
      </Card>
    </main>
  );
}
