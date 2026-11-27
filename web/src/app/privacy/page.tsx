import type { Metadata } from "next";

import { legalLocale } from "@/legal/content";
import { LegalView, legalMetadata } from "@/legal/legal-view";

export async function generateMetadata({ searchParams }: PageProps<"/privacy">): Promise<Metadata> {
  return legalMetadata("privacy", legalLocale((await searchParams).lang));
}

export default async function Page({ searchParams }: PageProps<"/privacy">) {
  return <LegalView page="privacy" locale={legalLocale((await searchParams).lang)} />;
}
