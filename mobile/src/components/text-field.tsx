import { feedbackGlyph, fontSize, minTouchTarget, radius, space } from "@labtrack/shared";
import type { ComponentRef, ReactNode, Ref } from "react";
import { Platform, StyleSheet, TextInput, type TextInputProps, View } from "react-native";
import { Text } from "@/components/app-text";

import { fonts } from "@/theme/fonts";
import { usePalette } from "@/theme/use-palette";

export type TextFieldRef = ComponentRef<typeof TextInput>;

export interface TextFieldProps
  extends Omit<TextInputProps, "style" | "accessibilityLabel" | "ref"> {
  label: string;
  error?: string;
  hint?: string;
  /** Rendered inside the field on the trailing edge (e.g. show/hide password). */
  trailing?: ReactNode;
  /** Lets forms move focus (next field, first invalid field). */
  inputRef?: Ref<TextFieldRef>;
}

export function TextField({ label, error, hint, trailing, inputRef, ...input }: TextFieldProps) {
  const p = usePalette();
  return (
    <View style={styles.wrap}>
      <Text style={[styles.label, { color: p.text }]}>{label}</Text>
      <View
        style={[
          styles.field,
          { borderColor: error ? p.danger : p.inputBorder, backgroundColor: p.surface },
        ]}
      >
        <TextInput
          ref={inputRef}
          accessibilityLabel={label}
          accessibilityHint={error ?? hint}
          placeholderTextColor={p.textMuted}
          style={[styles.input, { color: p.text }]}
          {...input}
        />
        {trailing}
      </View>
      {hint && !error && <Text style={[styles.note, { color: p.textMuted }]}>{hint}</Text>}
      {error && (
        <Text accessibilityLiveRegion="polite" style={[styles.note, { color: p.text }]}>
          {`${feedbackGlyph.error} ${error}`}
        </Text>
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: { gap: space.xs },
  label: { fontSize: fontSize.body, fontWeight: "600" },
  field: {
    flexDirection: "row",
    alignItems: "center",
    borderWidth: StyleSheet.hairlineWidth * 2,
    borderRadius: radius.md,
    minHeight: Platform.OS === "ios" ? minTouchTarget.ios : minTouchTarget.android,
  },
  input: {
    flex: 1,
    fontSize: fontSize.body,
    fontFamily: fonts.regular,
    paddingHorizontal: space.md,
    paddingVertical: space.sm,
  },
  note: { fontSize: fontSize.caption, lineHeight: fontSize.caption * 1.4 },
});
