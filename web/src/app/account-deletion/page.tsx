import type { Metadata } from "next";

import { legalLocale } from "@/legal/content";
import { LegalView, legalMetadata } from "@/legal/legal-view";

export async function generateMetadata({
  searchParams,
}: PageProps<"/account-deletion">): Promise<Metadata> {
  return legalMetadata("deletion", legalLocale((await searchParams).lang));
}

export default async function Page({ searchParams }: PageProps<"/account-deletion">) {
  return <LegalView page="deletion" locale={legalLocale((await searchParams).lang)} />;
}
