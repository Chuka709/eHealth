import mn from "@labtrack/shared/messages/mn.json";
import type { Metadata } from "next";
import { NextIntlClientProvider } from "next-intl";
import { getTranslations } from "next-intl/server";
import { Suspense } from "react";

export async function generateMetadata(): Promise<Metadata> {
  const t = await getTranslations("web.share");
  return {
    title: `LabTrack MN — ${t("title")}`,
    robots: { index: false, follow: false },
    referrer: "no-referrer",
  };
}

// A share link's viewer (7.3): per request (the viewing cookie, the CSP nonce), never indexed.
export default function ShareLayout({ children }: LayoutProps<"/s">) {
  return (
    <Suspense
      fallback={
        <p role="status" className="p-6">
          {mn.app.common.loading}
        </p>
      }
    >
      <NextIntlClientProvider>
        <div className="flex min-h-full flex-col bg-slate-50 text-slate-900 [color-scheme:light]">
          {children}
        </div>
      </NextIntlClientProvider>
    </Suspense>
  );
}
