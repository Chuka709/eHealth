import { useState } from "react";
import { useTranslations } from "use-intl";

import { Button } from "@/components/button";
import { FormMessage } from "@/components/form-message";
import { Screen } from "@/components/screen";
import { Paragraph, Title } from "@/components/text";
import { signOut } from "@/features/auth/session";
import { ConsentCard } from "@/features/consents/consent-card";
import {
  AI_KINDS,
  bundleOutdated,
  type ConsentState,
  consentItems,
  REQUIRED_KINDS,
  useConsents,
  useGiveConsents,
} from "@/features/consents/use-consents";
import { ApiError, useErrorText } from "@/lib/use-error-text";

type RequiredKind = (typeof REQUIRED_KINDS)[number];

/**
 * Consents (docs/04 §5, hazard H21). Required: terms, privacy, sensitive data — nothing is stored
 * without them. Optional: the AI pair (processing + transfer abroad), off by default. Asked again
 * whenever a text version changes; switches start from what is already given for this version.
 */
export default function ConsentsScreen() {
  const t = useTranslations("app.consent");
  const tCommon = useTranslations("app.common");
  const { data: states = [] } = useConsents();
  if (bundleOutdated(states)) {
    // The server shows a newer text than this build contains: consenting here would record a
    // version the user never read.
    return (
      <Screen>
        <Title>{t("title")}</Title>
        <FormMessage kind="warning" text={t("appOutdated")} />
        <Button variant="secondary" label={tCommon("signOut")} onPress={() => void signOut()} />
      </Screen>
    );
  }
  // A new version (or a fresh state after a conflict) starts the switches over.
  return (
    <ConsentForm key={states.map((s) => `${s.kind}:${s.current_version}`).join()} states={states} />
  );
}

function ConsentForm({ states }: { states: readonly ConsentState[] }) {
  const t = useTranslations("app.consent");
  const tCommon = useTranslations("app.common");
  const errorText = useErrorText();
  const give = useGiveConsents();
  const granted = (kind: string) => states.some((s) => s.kind === kind && s.granted);

  const [required, setRequired] = useState<Record<RequiredKind, boolean>>(() => ({
    terms: granted("terms"),
    privacy: granted("privacy"),
    sensitive_data: granted("sensitive_data"),
  }));
  const [ai, setAi] = useState(() => AI_KINDS.every(granted));
  const [missing, setMissing] = useState(false);
  const [declined, setDeclined] = useState(false);

  // Seen before but not for the current version: the text changed.
  const updated = states.some((s) => s.required && !s.granted && s.granted_version !== null);
  const draft = states.some((s) => s.current_version.startsWith("draft-"));
  const outdated = give.error instanceof ApiError && give.error.code === "consent.version_outdated";

  if (declined) {
    return (
      <Screen>
        <Title>{t("title")}</Title>
        <Paragraph>{t("declined")}</Paragraph>
        <Button label={t("backToConsents")} onPress={() => setDeclined(false)} />
        <Button variant="secondary" label={tCommon("signOut")} onPress={() => void signOut()} />
      </Screen>
    );
  }

  return (
    <Screen>
      <Title>{t("title")}</Title>
      {updated && <FormMessage kind="warning" text={t("updated")} />}
      <Paragraph>{t("intro")}</Paragraph>
      {draft && <Paragraph muted>{t("draft")}</Paragraph>}
      {REQUIRED_KINDS.map((kind) => (
        <ConsentCard
          key={kind}
          textKey={kind}
          required
          value={required[kind]}
          missing={missing && !required[kind]}
          onChange={(value) => {
            setMissing(false);
            setRequired((current) => ({ ...current, [kind]: value }));
          }}
        />
      ))}
      <ConsentCard textKey="ai" required={false} value={ai} onChange={setAi} />
      {missing && <FormMessage kind="error" text={t("needAll")} />}
      {give.isError && (
        <FormMessage kind="error" text={outdated ? t("outdated") : errorText(give.error)} />
      )}
      <Button
        label={t("continue")}
        busy={give.isPending}
        onPress={() => {
          if (!REQUIRED_KINDS.every((kind) => required[kind])) {
            setMissing(true);
            return;
          }
          // On success the refreshed states open the app (guard in (app)/_layout).
          give.mutate(consentItems(states, ai));
        }}
      />
      <Button variant="secondary" label={t("decline")} onPress={() => setDeclined(true)} />
    </Screen>
  );
}
