import { useEffect, useState } from "react";
import { AccessibilityInfo } from "react-native";
import { useTranslations } from "use-intl";

import { Button } from "@/components/button";
import { FormMessage } from "@/components/form-message";
import { Screen } from "@/components/screen";
import { Paragraph, Title } from "@/components/text";
import { readUnlockGate } from "@/features/auth/secure-tokens";
import { signOut } from "@/features/auth/session";
import { setLocked } from "@/features/lock/lock-store";

/**
 * Biometric lock (docs/04 §1). The only screen while locked; nothing signed-in is mounted. A
 * changed biometric enrollment invalidates the unlock key: only a password sign-in remains.
 * The user can never get stuck: the sign-out path is there in every state.
 */
export default function LockScreen() {
  const t = useTranslations("app.lock");
  const [state, setState] = useState<"idle" | "busy" | "failed" | "changed">("idle");

  const unlock = async () => {
    setState("busy");
    const result = await readUnlockGate(t("prompt"));
    if (result === "ok") setLocked(false);
    else setState(result === "invalidated" ? "changed" : "failed");
  };

  // biome-ignore lint/correctness/useExhaustiveDependencies: ask once when the screen opens
  useEffect(() => {
    // With a screen reader the system prompt would cut off the heading: let the user read the
    // screen and press Unlock. Otherwise ask right away (once; a cancel must not loop).
    void AccessibilityInfo.isScreenReaderEnabled()
      .catch(() => false)
      .then((reader) => {
        if (!reader) void unlock();
      });
  }, []);

  return (
    <Screen>
      <Title>{t("title")}</Title>
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
