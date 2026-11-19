"use client";

import { useTranslations } from "next-intl";
import { useActionState, useEffect, useRef, useState } from "react";

import { Alert, Button, Field, Input } from "@/components/ui";

import { openShare } from "./actions";

/**
 * The link's token is in the URL fragment (`/s#<token>`): browsers never send a fragment to a
 * server, nor in a Referer. It is read here once, then removed from the address bar and the
 * history, and goes to the server only with the PIN.
 */
export function PinForm() {
  const t = useTranslations("web.share");
  const [token, setToken] = useState<string | null>(null);
  const [state, action, pending] = useActionState(openShare, null);
  const read = useRef(false);

  useEffect(() => {
    if (read.current) return; // once (a second run would find the fragment already removed)
    read.current = true;
    const fromHash = window.location.hash.replace(/^#/, "");
    setToken(fromHash);
    if (fromHash) window.history.replaceState(null, "", window.location.pathname);
  }, []);
  useEffect(() => {
    if (state?.ok) window.location.replace("/s/view");
  }, [state]);

  if (token === null) return null; // until the fragment is read
  if (!/^[A-Za-z0-9_-]{43}$/.test(token)) {
    return <Alert tone="warn">{t("noLink")}</Alert>;
  }
  return (
    <form action={action} className="flex flex-col gap-4">
      <input type="hidden" name="token" value={token} />
      <Field label={t("pin")} htmlFor="pin">
        <Input
          id="pin"
          name="pin"
          inputMode="numeric"
          autoComplete="one-time-code"
          pattern="\s*[0-9]{3}\s?[0-9]{3}\s*"
          maxLength={8}
          required
          aria-describedby="pin-hint"
        />
      </Field>
      <p id="pin-hint" className="text-sm text-slate-700">
        {t("pinHint")}
      </p>
      {state && !state.ok ? (
        <Alert tone="danger">{state.code === "too_many" ? t("tooMany") : t("openFailed")}</Alert>
      ) : null}
      <Button type="submit" disabled={pending}>
        {pending ? t("opening") : t("open")}
      </Button>
    </form>
  );
}
