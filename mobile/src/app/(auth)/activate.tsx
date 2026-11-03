import { zodResolver } from "@hookform/resolvers/zod";
import * as Linking from "expo-linking";
import { useGlobalSearchParams, useRouter } from "expo-router";
import { useEffect, useMemo, useState } from "react";
import { Controller, useForm } from "react-hook-form";
import { useTranslations } from "use-intl";
import { z } from "zod";

import { Button } from "@/components/button";
import { FormMessage } from "@/components/form-message";
import { PasswordField } from "@/components/password-field";
import { Screen } from "@/components/screen";
import { StrengthMeter } from "@/components/strength-meter";
import { Paragraph, Title } from "@/components/text";
import { TextField } from "@/components/text-field";
import {
  takeActivationTokenFromUrl,
  takePendingActivationToken,
} from "@/features/auth/activation-link";
import {
  MAX_PASSWORD_LENGTH,
  MIN_PASSWORD_LENGTH,
  passwordScore,
} from "@/features/auth/password-strength";
import { ActivationQrScanner } from "@/features/auth/qr-scanner";
import { useActivate } from "@/features/auth/use-activate";
import { usernameSchema } from "@/features/auth/username";
import { ApiError, useErrorText } from "@/lib/use-error-text";

const schema = z
  .object({
    username: usernameSchema,
    password: z
      .string()
      .min(MIN_PASSWORD_LENGTH, "password.too_short")
      .max(MAX_PASSWORD_LENGTH, "password.too_long"),
    confirm: z.string(),
  })
  .refine((v) => v.password === v.confirm, { path: ["confirm"], message: "mismatch" });

const isPolicyError = (error: unknown) =>
  error instanceof ApiError && Boolean(error.code?.startsWith("password."));

export default function ActivateScreen() {
  const t = useTranslations();
  const router = useRouter();
  const errorText = useErrorText();
  const activate = useActivate();
  // From +native-intent (link/QR opened outside the app), else scanned in-app below.
  const [token, setToken] = useState(takePendingActivationToken);
  const linkingUrl = Linking.useLinkingURL();
  const params = useGlobalSearchParams();
  useEffect(() => {
    // Fallback if the router delivered the link without our intent rewrite. Never replace a
    // token the user is already working with (another app could send a link meanwhile).
    const fromLink = takeActivationTokenFromUrl(linkingUrl);
    if (fromLink) setToken((current) => current ?? fromLink);
  }, [linkingUrl]);
  useEffect(() => {
    // ...and in that case the router may have put the fragment into params: drop it.
    if ("#" in params) router.setParams({ "#": undefined });
  }, [params, router]);

  const { control, handleSubmit, formState, watch, setError, setFocus } = useForm({
    resolver: zodResolver(schema),
    defaultValues: { username: "", password: "", confirm: "" },
  });
  const password = watch("password");
  const score = useMemo(() => passwordScore(password), [password]);

  const submit = handleSubmit((values) => {
    if (!token) return;
    activate.mutate(
      { token, username: values.username, password: values.password },
      {
        onSuccess: () => router.replace({ pathname: "/login", params: { activated: "1" } }),
        onError: (error) => {
          // Policy problems belong under the field; anything else is shown by the button.
          if (error instanceof ApiError && isPolicyError(error)) {
            setError("password", { message: error.code ?? "" }, { shouldFocus: true });
          }
        },
      },
    );
  });

  const fieldError = (message: string | undefined) => {
    if (!message) return undefined;
    return message === "mismatch" ? t("app.activate.mismatch") : t(`error.${message}`);
  };
  const tokenRejected =
    activate.error instanceof ApiError && activate.error.code === "auth.activation_invalid";
  const formError =
    activate.isError && !isPolicyError(activate.error) ? errorText(activate.error) : null;

  if (!token) {
    return (
      <Screen>
        <Title>{t("app.activate.title")}</Title>
        <ActivationQrScanner onToken={setToken} />
      </Screen>
    );
  }

  if (tokenRejected) {
    return (
      <Screen>
        <Title>{t("app.activate.title")}</Title>
        <FormMessage kind="error" text={errorText(activate.error)} />
        <Button
          label={t("app.activate.scanAgain")}
          onPress={() => {
            activate.reset();
            setToken(null);
          }}
        />
      </Screen>
    );
  }

  return (
    <Screen>
      <Title>{t("app.activate.title")}</Title>
      <Paragraph>{t("app.activate.codeReady")}</Paragraph>
      <Controller
        control={control}
        name="username"
        render={({ field }) => (
          <TextField
            inputRef={field.ref}
            label={t("app.activate.username")}
            hint={t("app.activate.usernameHint")}
            value={field.value}
            onChangeText={field.onChange}
            onBlur={field.onBlur}
            error={
              formState.errors.username?.message
                ? t(`app.common.${formState.errors.username.message}`)
                : undefined
            }
            autoCapitalize="none"
            autoCorrect={false}
            spellCheck={false}
            autoComplete="username"
            textContentType="username"
            returnKeyType="next"
            submitBehavior="submit"
            onSubmitEditing={() => setFocus("password")}
          />
        )}
      />
      <Controller
        control={control}
        name="password"
        render={({ field }) => (
          <PasswordField
            purpose="new"
            inputRef={field.ref}
            label={t("app.activate.password")}
            hint={t("app.activate.rules")}
            value={field.value}
            onChangeText={field.onChange}
            onBlur={field.onBlur}
            error={fieldError(formState.errors.password?.message)}
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
            label={t("app.activate.confirm")}
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
      {formError && <FormMessage kind="error" text={formError} />}
      <Button
        label={t("app.activate.submit")}
        busy={activate.isPending}
        onPress={() => void submit()}
      />
    </Screen>
  );
}
