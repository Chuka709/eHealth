import { useEffect, useState } from "react";
import { AccessibilityInfo } from "react-native";
import { useTranslations } from "use-intl";

import { Button } from "@/components/button";
import { FormMessage } from "@/components/form-message";
import { Screen } from "@/components/screen";
import { Paragraph, Title } from "@/components/text";
import { readUnlockGate } from "@/features/auth/secure-tokens";
import { signOut } from "@/features/auth/session";
import { EmergencyCardPanel } from "@/features/emergency/card-panel";
import { type LockedCard, lockedCards } from "@/features/emergency/use-unlocked-card";
import { setLocked } from "@/features/lock/lock-store";

/**
 * Biometric lock (docs/04 §1). The only screen while locked; nothing signed-in is mounted. A
 * changed biometric enrollment invalidates the unlock key: only a password sign-in remains.
 * The user can never get stuck: the sign-out path is there in every state.
 *
 * If the user allowed it (Settings, off by default — H17), the saved emergency card can be opened
 * here without unlocking. It is read from the encrypted store only: no API call, no other
 * screen, nothing else of the account (H22).
 */
export default function LockScreen() {
  const t = useTranslations("app.lock");
  const e = useTranslations("app.emergency");
  const [state, setState] = useState<"idle" | "busy" | "failed" | "changed">("idle");
  const [cards, setCards] = useState<LockedCard[]>([]);
  const [shown, setShown] = useState<LockedCard | null>(null);

  const unlock = async () => {
    setState("busy");
    const result = await readUnlockGate(t("prompt"));
    if (result === "ok") setLocked(false);
    else setState(result === "invalidated" ? "changed" : "failed");
  };

  // biome-ignore lint/correctness/useExhaustiveDependencies: ask once when the screen opens
  useEffect(() => {
    let live = true;
    // The allowed emergency cards first. With one, the system prompt is not raised by itself:
    // it would cover the 🆘 button from a team that does not know to cancel it (the owner
    // presses Unlock). With a screen reader the prompt would cut off the heading: the user
    // presses Unlock. Otherwise ask right away (once; a cancel must not loop).
    void Promise.all([
      lockedCards().catch(() => [] as LockedCard[]),
      AccessibilityInfo.isScreenReaderEnabled().catch(() => false),
    ]).then(([found, reader]) => {
      if (!live) return;
      setCards(found);
      if (!reader && found.length === 0) void unlock();
    });
    return () => {
      live = false;
    };
  }, []);

  if (shown) {
    // the card first (its title in the card's language); the way back after it
    return (
      <Screen>
        <EmergencyCardPanel card={shown.card} copy="saved" top={<CardHeading />} />
        <Button variant="secondary" label={e("backToLock")} onPress={() => setShown(null)} />
      </Screen>
    );
  }

  return (
    <Screen>
      <Title>{t("title")}</Title>
      {/* in both languages: the team may not read Mongolian */}
      {cards.map((c) => (
        <Button
          key={c.id}
          variant="danger"
          label={
            cards.length === 1 ? e("lockOpen") : `${e("lockOpen")} — ${c.card.patient.full_name}`
          }
          accessibilityLabel={
            cards.length === 1
              ? e("lockOpenLabel")
              : `${e("lockOpenLabel")} — ${c.card.patient.full_name}`
          }
          onPress={() => setShown(c)}
        />
      ))}
      {state === "changed" ? (
        <FormMessage kind="warning" text={t("changed")} />
      ) : (
        <>
          <Paragraph>{t("body")}</Paragraph>
          {state === "failed" && <FormMessage kind="error" text={t("failed")} />}
          <Button label={t("unlock")} busy={state === "busy"} onPress={() => void unlock()} />
        </>
      )}
      {/* Signs out fully (wipes the session): the password is the fallback, not the phone PIN. */}
      <Button
        variant={state === "changed" ? "primary" : "secondary"}
        label={t("usePassword")}
        disabled={state === "busy"}
        onPress={() => void signOut()}
      />
    </Screen>
  );
}

function CardHeading() {
  const e = useTranslations("app.emergency");
  return <Title>{e("title")}</Title>;
}
