import { zodResolver } from "@hookform/resolvers/zod";
import { useLocalSearchParams, useRouter } from "expo-router";
import { usePreventScreenCapture } from "expo-screen-capture";
import { Controller, useForm } from "react-hook-form";
import { useTranslations } from "use-intl";
import { z } from "zod";

import { Button } from "@/components/button";
import { FormMessage } from "@/components/form-message";
import { PasswordField } from "@/components/password-field";
import { Screen } from "@/components/screen";
import { Title } from "@/components/text";
import { TextField } from "@/components/text-field";
import { useAppSwitcherProtection } from "@/features/auth/use-app-switcher-protection";
import { useLogin } from "@/features/auth/use-login";
import { useErrorText } from "@/lib/use-error-text";

const schema = z.object({
  username: z.string().trim().min(1),
  password: z.string().min(1),
});

export default function LoginScreen() {
  usePreventScreenCapture("login");
  useAppSwitcherProtection();
  const t = useTranslations("app");
  const router = useRouter();
  const errorText = useErrorText();
  // Set only by our own activate screen: external links cannot carry params (+native-intent).
  const { activated } = useLocalSearchParams<{ activated?: string }>();
  const login = useLogin();
  const { control, handleSubmit, formState, setFocus } = useForm({
    resolver: zodResolver(schema),
    defaultValues: { username: "", password: "" },
  });
  const required = t("common.fieldRequired");

  // On success the session status flips and the guarded root stack shows the app.
  const submit = handleSubmit((values) => login.mutate(values));

  return (
    <Screen>
      <Title>{t("login.title")}</Title>
      {activated === "1" && !login.isError && (
        <FormMessage kind="success" text={t("activate.done")} />
      )}
      <Controller
        control={control}
        name="username"
        render={({ field }) => (
          <TextField
            inputRef={field.ref}
            label={t("login.username")}
            value={field.value}
            onChangeText={field.onChange}
            onBlur={field.onBlur}
            error={formState.errors.username ? required : undefined}
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
            purpose="current"
            inputRef={field.ref}
            label={t("login.password")}
            value={field.value}
            onChangeText={field.onChange}
            onBlur={field.onBlur}
            error={formState.errors.password ? required : undefined}
            returnKeyType="go"
            onSubmitEditing={() => void submit()}
          />
        )}
      />
      {/* Next to the button, where the user is looking after pressing it. */}
      {login.isError && <FormMessage kind="error" text={errorText(login.error)} />}
      <Button label={t("login.submit")} busy={login.isPending} onPress={() => void submit()} />
      <Button variant="link" label={t("login.forgot")} onPress={() => router.push("/forgot")} />
    </Screen>
  );
}
