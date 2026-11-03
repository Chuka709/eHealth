import { Host, Switch } from "@expo/ui";
import { zodResolver } from "@hookform/resolvers/zod";
import { useMemo, useState } from "react";
import { Controller, useForm } from "react-hook-form";
import { StyleSheet } from "react-native";
import { useTranslations } from "use-intl";
import { z } from "zod";

import { Button } from "@/components/button";
import { FormMessage } from "@/components/form-message";
import { PasswordField } from "@/components/password-field";
import { Screen } from "@/components/screen";
import { StrengthMeter } from "@/components/strength-meter";
import { Paragraph } from "@/components/text";
import {
  MAX_PASSWORD_LENGTH,
  MIN_PASSWORD_LENGTH,
  passwordScore,
} from "@/features/auth/password-strength";
import { useChangePassword } from "@/features/auth/use-change-password";
import { ApiError, useErrorText } from "@/lib/use-error-text";

const schema = z
  .object({
    current: z.string().min(1, "fieldRequired"),
    next: z
      .string()
      .min(MIN_PASSWORD_LENGTH, "password.too_short")
      .max(MAX_PASSWORD_LENGTH, "password.too_long"),
    confirm: z.string(),
  })
  .refine((v) => v.next === v.confirm, { path: ["confirm"], message: "mismatch" });

export default function ChangePasswordScreen() {
  const t = useTranslations();
  const errorText = useErrorText();
  const change = useChangePassword();
  const [signOutOthers, setSignOutOthers] = useState(true);
  const [done, setDone] = useState<null | "kept" | "others">(null);
  const { control, handleSubmit, formState, watch, setError, setFocus, reset } = useForm({
    resolver: zodResolver(schema),
    defaultValues: { current: "", next: "", confirm: "" },
  });
  const next = watch("next");
  const score = useMemo(() => passwordScore(next), [next]);

  const submit = handleSubmit((values) => {
    setDone(null);
    change.submit(
      { current: values.current, next: values.next, signOutOthers },
      {
        onSuccess: () => {
          reset(); // no password stays in the form
          setDone(signOutOthers ? "others" : "kept");
        },
        onError: (error) => {
          if (!(error instanceof ApiError)) return;
          // A wrong current password is the user's to fix here (it does not end the session).
          if (error.code === "auth.invalid_credentials") {
            setError("current", { message: "currentWrong" }, { shouldFocus: true });
          } else if (error.code?.startsWith("password.")) {
            setError("next", { message: error.code }, { shouldFocus: true });
          }
        },
      },
    );
  });

  const fieldError = (message: string | undefined) => {
    if (!message) return undefined;
    if (message === "mismatch") return t("app.activate.mismatch");
    if (message === "fieldRequired") return t("app.common.fieldRequired");
    if (message === "currentWrong") return t("app.passwordChange.currentWrong");
    return t(`error.${message}`);
  };
  const handled =
    change.error instanceof ApiError &&
    (change.error.code === "auth.invalid_credentials" ||
      Boolean(change.error.code?.startsWith("password.")));

  return (
    <Screen>
      <Controller
        control={control}
        name="current"
        render={({ field }) => (
          <PasswordField
            purpose="current"
            inputRef={field.ref}
            label={t("app.passwordChange.current")}
            value={field.value}
            onChangeText={field.onChange}
            onBlur={field.onBlur}
            error={fieldError(formState.errors.current?.message)}
            returnKeyType="next"
            submitBehavior="submit"
            onSubmitEditing={() => setFocus("next")}
          />
        )}
      />
      <Controller
        control={control}
        name="next"
        render={({ field }) => (
          <PasswordField
            purpose="new"
            inputRef={field.ref}
            label={t("app.passwordChange.new")}
            hint={t("app.activate.rules")}
            value={field.value}
            onChangeText={field.onChange}
            onBlur={field.onBlur}
            error={fieldError(formState.errors.next?.message)}
            maxLength={MAX_PASSWORD_LENGTH}
            returnKeyType="next"
            submitBehavior="submit"
            onSubmitEditing={() => setFocus("confirm")}
          />
        )}
      />
      <StrengthMeter score={score} />
      <Controller
        control={control}
        name="confirm"
        render={({ field }) => (
          <PasswordField
            purpose="new"
            inputRef={field.ref}
            label={t("app.passwordChange.confirm")}
            value={field.value}
            onChangeText={field.onChange}
            onBlur={field.onBlur}
            error={fieldError(formState.errors.confirm?.message)}
            maxLength={MAX_PASSWORD_LENGTH}
            returnKeyType="done"
            onSubmitEditing={() => void submit()}
          />
        )}
      />
      <Host matchContents={{ vertical: true }} style={styles.wide}>
        <Switch
          label={t("app.passwordChange.signOutOthers")}
          value={signOutOthers}
          onValueChange={setSignOutOthers}
          testID="password-sign-out-others"
        />
      </Host>
      <Paragraph muted>{t("app.passwordChange.signOutOthersHint")}</Paragraph>
      {/* Feedback next to the button, where the user is after pressing it. */}
      {change.isError && !handled && <FormMessage kind="error" text={errorText(change.error)} />}
      {done && (
        <FormMessage
          kind="success"
          text={t(done === "others" ? "app.passwordChange.doneOthers" : "app.passwordChange.done")}
        />
      )}
      <Button
        label={t("app.passwordChange.submit")}
        busy={change.isPending}
        onPress={() => void submit()}
      />
    </Screen>
  );
}

const styles = StyleSheet.create({ wide: { width: "100%" } });
