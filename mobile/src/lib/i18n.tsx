import en from "@labtrack/shared/messages/en.json";
import mn from "@labtrack/shared/messages/mn.json";
import type { ReactNode } from "react";
import { IntlProvider } from "use-intl";

const messages = { mn, en } as const;
export type Locale = keyof typeof messages;

/** Mongolian is the default UI language (CLAUDE.md); English is secondary. */
export function I18nProvider({
  locale = "mn",
  children,
}: {
  locale?: Locale;
  children: ReactNode;
}) {
  return (
    <IntlProvider locale={locale} messages={messages[locale]} timeZone="Asia/Ulaanbaatar">
      {children}
    </IntlProvider>
  );
}
