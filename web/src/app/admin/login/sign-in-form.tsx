"use client";

import { useTranslations } from "next-intl";
import { useActionState } from "react";

import { Alert, Button, Field, Input } from "@/components/ui";

import { signIn } from "../actions";

export function SignInForm() {
  const t = useTranslations();
  const [state, action, pending] = useActionState(signIn, null);
  return (
    <form action={action} className="flex flex-col gap-4">
      <Field label={t("admin.login.username")} htmlFor="username">
        <Input
          id="username"
          name="username"
          autoComplete="username"
          autoCapitalize="none"
          required
        />
      </Field>
      <Field label={t("admin.login.password")} htmlFor="password">
        <Input
          id="password"
          name="password"
          type="password"
          autoComplete="current-password"
          required
        />
      </Field>
      <Field label={t("admin.login.totp")} htmlFor="totp_code">
        <Input
          id="totp_code"
          name="totp_code"
          inputMode="numeric"
          autoComplete="one-time-code"
          pattern="[0-9 ]{6,7}"
          maxLength={7}
          required
        />
      </Field>
      {state && !state.ok ? <Alert tone="danger">{t(`error.${state.code}`)}</Alert> : null}
      <Button type="submit" disabled={pending}>
        {pending ? t("admin.common.saving") : t("admin.login.submit")}
      </Button>
    </form>
  );
}
