import { useRef, useState } from "react";
import { Alert } from "react-native";
import { useTranslations } from "use-intl";

import { Button } from "@/components/button";
import { FormMessage } from "@/components/form-message";
import { PasswordField } from "@/components/password-field";
import { Screen } from "@/components/screen";
import { Paragraph } from "@/components/text";
import type { TextFieldRef } from "@/components/text-field";
import { useDeleteAccount } from "@/features/me/use-account";
import { formatDate } from "@/lib/dates";
import { ApiError, useErrorText } from "@/lib/use-error-text";

/** Account deletion from inside the app (App Store / Play requirement, docs/04 §1). */
export default function DeleteAccountScreen() {
  const t = useTranslations("app");
  const errorText = useErrorText();
  const remove = useDeleteAccount();
  const [password, setPassword] = useState("");
  const [missing, setMissing] = useState(false);
  const field = useRef<TextFieldRef>(null);
  const wrong =
    remove.error instanceof ApiError && remove.error.code === "auth.invalid_credentials";

  const confirmDelete = () => {
    if (!password) {
      setMissing(true);
      return;
    }
    // The server sets the exact date (30 days); the dialog names it so the step is concrete.
    const around = formatDate(new Date(Date.now() + 30 * 86_400_000).toISOString());
    Alert.alert(
      t("deleteAccount.confirmTitle"),
      t("deleteAccount.confirmBody", { date: around }),
      [
        { text: t("common.cancel"), style: "cancel" },
        {
          text: t("deleteAccount.confirm"),
          style: "destructive",
          // On success the device is wiped and the deletion notice is shown.
          onPress: () =>
            remove.submit(password, {
              onError: () => {
                setPassword("");
                field.current?.focus();
              },
            }),
        },
      ],
      { cancelable: true },
    );
  };

  return (
    <Screen>
      <Paragraph>{t("deleteAccount.what")}</Paragraph>
      <Paragraph>{t("deleteAccount.shared")}</Paragraph>
      <Paragraph muted>{t("deleteAccount.undo")}</Paragraph>
      <PasswordField
        purpose="current"
        inputRef={field}
        label={t("deleteAccount.password")}
        value={password}
        onChangeText={(value) => {
          setMissing(false);
          setPassword(value);
        }}
        error={
          missing ? t("common.fieldRequired") : wrong ? t("deleteAccount.passwordWrong") : undefined
        }
        returnKeyType="done"
        onSubmitEditing={confirmDelete}
      />
      {remove.isError && !wrong && <FormMessage kind="error" text={errorText(remove.error)} />}
      <Button
        variant="danger"
        label={t("deleteAccount.submit")}
        busy={remove.isPending}
        onPress={confirmDelete}
      />
    </Screen>
  );
}
