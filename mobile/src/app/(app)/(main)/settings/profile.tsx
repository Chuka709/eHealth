import { zodResolver } from "@hookform/resolvers/zod";
import { fontSize, space } from "@labtrack/shared";
import { Controller, useForm } from "react-hook-form";
import { StyleSheet, View } from "react-native";
import { useTranslations } from "use-intl";
import { z } from "zod";
import { Text } from "@/components/app-text";
import { Button } from "@/components/button";
import { FormMessage } from "@/components/form-message";
import { Screen } from "@/components/screen";
import { LoadingView, RetryView } from "@/components/state-view";
import { Paragraph } from "@/components/text";
import { TextField } from "@/components/text-field";
import { type Me, useMe, useUpdateMe } from "@/features/me/use-me";
import { ApiError, useErrorText } from "@/lib/use-error-text";
import { usePalette } from "@/theme/use-palette";

const schema = z.object({
  displayName: z.string().trim().min(1, "displayNameRequired").max(80, "displayNameInvalid"),
});

export default function ProfileScreen() {
  const errorText = useErrorText();
  const me = useMe();
  if (me.isPending) return <LoadingView />;
  if (!me.data) return <RetryView text={errorText(me.error)} onRetry={() => void me.refetch()} />;
  return <ProfileForm me={me.data} />;
}

function ProfileForm({ me }: { me: Me }) {
  const t = useTranslations("app");
  const p = usePalette();
  const errorText = useErrorText();
  // Separate requests, separate feedback: saving the name never reports on the language.
  const saveName = useUpdateMe();
  const saveLocale = useUpdateMe();
  const { control, handleSubmit, formState, setError, reset } = useForm({
    resolver: zodResolver(schema),
    defaultValues: { displayName: me.display_name },
  });
  const submit = handleSubmit(({ displayName }) =>
    saveName.mutate(
      { display_name: displayName },
      {
        onSuccess: (saved) => reset({ displayName: saved.display_name }),
        onError: (error) => {
          // The server refuses control or invisible characters in names (422).
          if (error instanceof ApiError && error.code === "validation") {
            setError("displayName", { message: "displayNameInvalid" }, { shouldFocus: true });
          }
        },
      },
    ),
  );
  const nameError = formState.errors.displayName?.message;
  const nameHandled = saveName.error instanceof ApiError && saveName.error.code === "validation";

  return (
    <Screen>
      <Paragraph muted>{t("profile.usernameValue", { username: me.username })}</Paragraph>
      <Controller
        control={control}
        name="displayName"
        render={({ field }) => (
          <TextField
            inputRef={field.ref}
            label={t("profile.displayName")}
            value={field.value}
            onChangeText={field.onChange}
            onBlur={field.onBlur}
            error={nameError ? t(`profile.${nameError}`) : undefined}
            maxLength={80}
            returnKeyType="done"
            onSubmitEditing={() => void submit()}
          />
        )}
      />
      {saveName.isError && !nameHandled && (
        <FormMessage kind="error" text={errorText(saveName.error)} />
      )}
      {saveName.isSuccess && !formState.isDirty && (
        <FormMessage kind="success" text={t("common.saved")} />
      )}
      <Button
        label={t("common.save")}
        busy={saveName.isPending}
        disabled={!formState.isDirty}
        onPress={() => void submit()}
      />

      <View
        accessibilityRole="radiogroup"
        accessibilityLabel={t("profile.language")}
        style={styles.group}
      >
        <Text accessibilityRole="header" style={[styles.heading, { color: p.text }]}>
          {t("profile.language")}
        </Text>
        {(["mn", "en"] as const).map((locale) => (
          <Button
            key={locale}
            variant="secondary"
            selected={me.locale === locale}
            label={t(`profile.${locale}`)}
            busy={saveLocale.isPending && saveLocale.variables?.locale === locale}
            onPress={() => {
              if (me.locale !== locale) saveLocale.mutate({ locale });
            }}
          />
        ))}
        {saveLocale.isError && <FormMessage kind="error" text={errorText(saveLocale.error)} />}
      </View>
    </Screen>
  );
}

const styles = StyleSheet.create({
  group: { gap: space.sm, marginTop: space.lg },
  heading: { fontSize: fontSize.bodyLarge, fontWeight: "600" },
});
