import type { Metadata } from "next";
import { NextIntlClientProvider } from "next-intl";
import { Suspense } from "react";

export const metadata: Metadata = {
  title: "LabTrack MN — Админ",
  robots: { index: false, follow: false },
  referrer: "no-referrer",
};

// Everything under /admin depends on the request (session cookie, locale, CSP nonce), so the
// whole tree renders per request inside this boundary.
export default function AdminLayout({ children }: LayoutProps<"/admin">) {
  return (
    <Suspense
      fallback={
        <p role="status" className="p-6">
          Ачаалж байна…
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
