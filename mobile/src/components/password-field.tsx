import { fontSize, minTouchTarget, space } from "@labtrack/shared";
import { useState } from "react";
import { Platform, Pressable, StyleSheet } from "react-native";
import { useTranslations } from "use-intl";
import { Text } from "@/components/app-text";

import { usePalette } from "@/theme/use-palette";

import { TextField, type TextFieldProps } from "./text-field";

type PasswordFieldProps = Omit<TextFieldProps, "secureTextEntry" | "trailing"> & {
  /** "new" for setting a password (password managers offer to generate/save one). */
  purpose: "current" | "new";
};

export function PasswordField({ purpose, ...field }: PasswordFieldProps) {
  const t = useTranslations("app.passwordField");
  const p = usePalette();
  const [visible, setVisible] = useState(false);
  return (
    <TextField
      {...field}
      secureTextEntry={!visible}
      autoCapitalize="none"
      autoCorrect={false}
      spellCheck={false}
      autoComplete={purpose === "new" ? "new-password" : "current-password"}
      textContentType={purpose === "new" ? "newPassword" : "password"}
      trailing={
        <Pressable
          onPress={() => setVisible((v) => !v)}
          accessibilityRole="button"
          accessibilityLabel={visible ? t("hide") : t("show")}
          style={styles.toggle}
        >
          {/* Short visible text keeps the input wide at large font sizes. */}
          <Text style={[styles.toggleText, { color: p.primary }]}>
            {visible ? t("hideShort") : t("showShort")}
          </Text>
        </Pressable>
      }
    />
  );
}

const styles = StyleSheet.create({
  toggle: {
    minHeight: Platform.OS === "ios" ? minTouchTarget.ios : minTouchTarget.android,
    minWidth: Platform.OS === "ios" ? minTouchTarget.ios : minTouchTarget.android,
    alignItems: "center",
    justifyContent: "center",
    paddingHorizontal: space.md,
  },
  toggleText: { fontSize: fontSize.caption, fontWeight: "600" },
});
