import { type ReactNode, useState } from "react";
import { useTranslations } from "use-intl";

import { Button } from "@/components/button";
import { I18nProvider, type Locale, useLocale } from "@/lib/i18n";

import { type CardCopy, EmergencyCardView } from "./emergency-card-view";
import type { EmergencyCard } from "./snapshot";

/**
 * The card in its own language provider, with a switch to the other language (a team abroad).
 * Shared by the card screen and the locked app. `top` renders inside the provider, so the
 * screen's title follows the card's language.
 */
export function EmergencyCardPanel({
  card,
  copy,
  top,
}: {
  card: EmergencyCard;
  copy: CardCopy;
  top?: ReactNode;
}) {
  const appLocale = useLocale();
  const [locale, setLocale] = useState<Locale | null>(null);
  const shown = locale ?? appLocale;
  return (
    <I18nProvider locale={shown}>
      {top}
      <SwitchLanguage onPress={() => setLocale(shown === "mn" ? "en" : "mn")} />
      <EmergencyCardView card={card} copy={copy} />
    </I18nProvider>
  );
}

// the other language, named in that language: the first thing a foreign team can read
function SwitchLanguage({ onPress }: { onPress: () => void }) {
  const e = useTranslations("app.emergency");
  return (
    <Button
      variant="secondary"
      label={e("switchTo")}
      accessibilityLabel={e("switchToLabel")}
      onPress={onPress}
    />
  );
}
