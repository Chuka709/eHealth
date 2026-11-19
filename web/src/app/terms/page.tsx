import type { Metadata } from "next";

import { legalLocale } from "@/legal/content";
import { LegalView, legalMetadata } from "@/legal/legal-view";

export async function generateMetadata({ searchParams }: PageProps<"/terms">): Promise<Metadata> {
  return legalMetadata("terms", legalLocale((await searchParams).lang));
}

export default async function Page({ searchParams }: PageProps<"/terms">) {
  return <LegalView page="terms" locale={legalLocale((await searchParams).lang)} />;
}
