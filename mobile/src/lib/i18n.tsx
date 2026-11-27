import en from "@labtrack/shared/messages/en.json";
import mn from "@labtrack/shared/messages/mn.json";
import { type ReactNode, useSyncExternalStore } from "react";
import { IntlProvider } from "use-intl";

const messages = { mn, en } as const;
export type Locale = keyof typeof messages;

// The signed-in user's language (from /me, changed in Profile); Mongolian otherwise.
let current: Locale = "mn";
const listeners = new Set<() => void>();

export function setLocale(next: Locale): void {
  if (next === current) return;
  current = next;
  for (const listener of listeners) listener();
}

const subscribe = (listener: () => void) => {
  listeners.add(listener);
  return () => listeners.delete(listener);
};
const getLocale = () => current;

/** The app's language (the user's choice), outside any provider that overrides it. */
export function useLocale(): Locale {
  return useSyncExternalStore(subscribe, getLocale, getLocale);
}

/** Mongolian is the default UI language (CLAUDE.md); English is secondary. */
export function I18nProvider({ locale, children }: { locale?: Locale; children: ReactNode }) {
  const chosen = useSyncExternalStore(subscribe, getLocale, getLocale);
  const active = locale ?? chosen;
  return (
    <IntlProvider locale={active} messages={messages[active]} timeZone="Asia/Ulaanbaatar">
      {children}
    </IntlProvider>
  );
}
