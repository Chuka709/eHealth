import en from "@labtrack/shared/messages/en.json";
import mn from "@labtrack/shared/messages/mn.json";
import { cookies } from "next/headers";
import { getRequestConfig } from "next-intl/server";

const catalogs = { mn, en } as const;
export type Locale = keyof typeof catalogs;

// Mongolian first (CLAUDE.md); English only when the admin chose it.
export default getRequestConfig(async () => {
  const chosen = (await cookies()).get("locale")?.value;
  const locale: Locale = chosen === "en" ? "en" : "mn";
  return { locale, messages: catalogs[locale], timeZone: "Asia/Ulaanbaatar" };
});
