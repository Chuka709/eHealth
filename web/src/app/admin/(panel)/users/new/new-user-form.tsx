"use client";

import { useTranslations } from "next-intl";
import { useActionState } from "react";

import { Alert, Button, Field, Input, Select } from "@/components/ui";

import { createUser } from "../actions";

export function NewUserForm() {
  const t = useTranslations();
  const [state, action, pending] = useActionState(createUser, null);
  return (
    <form action={action} className="flex max-w-lg flex-col gap-4">
      <Field label={t("admin.new.username")} htmlFor="username">
        <Input
          id="username"
          name="username"
          required
          pattern="[a-zA-Z0-9._]{3,32}"
          autoCapitalize="none"
          autoComplete="off"
        />
      </Field>
      <Field label={t("admin.new.display_name")} htmlFor="display_name">
        <Input id="display_name" name="display_name" required maxLength={100} autoComplete="off" />
      </Field>
      <Field label={t("admin.new.role")} htmlFor="role">
        <Select id="role" name="role" defaultValue="user">
          <option value="user">{t("admin.role.user")}</option>
          <option value="doctor">{t("admin.role.doctor")}</option>
        </Select>
      </Field>
      <Field label={t("admin.new.phone")} htmlFor="phone">
        <Input
          id="phone"
          name="phone"
          type="tel"
          inputMode="tel"
          maxLength={20}
          autoComplete="off"
        />
      </Field>
      <Field label={t("admin.new.national_id")} htmlFor="national_id">
        <Input id="national_id" name="national_id" maxLength={10} autoComplete="off" />
      </Field>
      {state && !state.ok ? <Alert tone="danger">{t(`error.${state.code}`)}</Alert> : null}
      <Button type="submit" disabled={pending} className="self-start">
        {pending ? t("admin.common.saving") : t("admin.new.submit")}
      </Button>
    </form>
  );
}
