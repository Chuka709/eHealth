import type { Metadata } from "next";
import Link from "next/link";

import { type Block, LEGAL, type LegalLocale, type LegalPage } from "./content";

const PATHS: Record<LegalPage, string> = {
  privacy: "/privacy",
  terms: "/terms",
  deletion: "/account-deletion",
};

const NAV: Record<LegalLocale, Record<LegalPage, string>> = {
  mn: { privacy: "Нууцлалын бодлого", terms: "Үйлчилгээний нөхцөл", deletion: "Аккаунт устгах" },
  en: { privacy: "Privacy policy", terms: "Terms of use", deletion: "Delete account" },
};

const UI = {
  mn: { switchTo: "English", updated: "Шинэчилсэн", nav: "Хуулийн баримтууд" },
  en: { switchTo: "Монгол", updated: "Updated", nav: "Legal documents" },
} as const;

// a 44 px touch target (as components/ui.tsx); the current page reads bold, not underlined
const link =
  "inline-flex min-h-11 items-center text-blue-800 underline hover:text-blue-950 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-blue-700 aria-[current=page]:font-bold aria-[current=page]:text-slate-900 aria-[current=page]:no-underline";

const href = (page: LegalPage, locale: LegalLocale) =>
  locale === "en" ? `${PATHS[page]}?lang=en` : PATHS[page];

/** Store reviewers and users must find these: indexed, unlike the rest of the site. */
export function legalMetadata(page: LegalPage, locale: LegalLocale): Metadata {
  const doc = LEGAL[page][locale];
  return {
    title: `LabTrack MN — ${doc.title}`,
    description: doc.description,
    robots: { index: true, follow: true },
    alternates: {
      canonical: href(page, locale),
      languages: { mn: href(page, "mn"), en: href(page, "en") },
    },
  };
}

function BlockView({ block }: { block: Block }) {
  if (typeof block === "string") return <p>{block}</p>;
  return (
    <ul className="list-disc space-y-1 pl-6">
      {block.map((item) => (
        <li key={item}>{item}</li>
      ))}
    </ul>
  );
}

/** One legal page: server-rendered text (the only script is Next's, under the nonce CSP). */
export function LegalView({ page, locale }: { page: LegalPage; locale: LegalLocale }) {
  const doc = LEGAL[page][locale];
  const ui = UI[locale];
  const other: LegalLocale = locale === "mn" ? "en" : "mn";
  return (
    <div
      lang={locale}
      className="flex min-h-full flex-col bg-white text-slate-900 [color-scheme:light]"
    >
      <header className="mx-auto flex w-full max-w-3xl flex-wrap items-center justify-between gap-3 px-4 pt-4 sm:px-8">
        <p className="font-semibold">LabTrack MN</p>
        <Link href={href(page, other)} hrefLang={other} lang={other} className={link}>
          {ui.switchTo}
        </Link>
      </header>
      <main className="mx-auto flex w-full max-w-3xl flex-col gap-6 break-words px-4 py-4 sm:px-8">
        <h1 className="text-2xl font-bold">{doc.title}</h1>
        {doc.draft && (
          <p
            role="note"
            className="rounded-md border border-amber-700 bg-amber-50 p-3 text-amber-950"
          >
            <span aria-hidden="true">⚠ </span>
            {doc.draft}
          </p>
        )}
        <p className="text-sm text-slate-700">
          {ui.updated}: {doc.updated}
        </p>
        {doc.sections.map((s) => (
          <section key={s.heading} className="flex flex-col gap-2 leading-relaxed">
            <h2 className="text-lg font-semibold">{s.heading}</h2>
            {s.blocks.map((b) => (
              <BlockView key={typeof b === "string" ? b : b.join("|")} block={b} />
            ))}
          </section>
        ))}
      </main>
      <footer className="mx-auto w-full max-w-3xl px-4 pb-6 sm:px-8">
        <nav aria-label={ui.nav} className="flex flex-wrap gap-x-6 border-t border-slate-300 pt-2">
          {(Object.keys(PATHS) as LegalPage[]).map((p) => (
            <Link
              key={p}
              href={href(p, locale)}
              aria-current={p === page ? "page" : undefined}
              className={link}
            >
              {NAV[locale][p]}
            </Link>
          ))}
        </nav>
      </footer>
    </div>
  );
}
