import type { ComponentProps } from "react";
import { Text as RNText, StyleSheet } from "react-native";

import { fontFor, fontState } from "@/theme/fonts";

/**
 * The app's Text: React Native's, in the app font (Golos Text) with the weight mapped to its
 * file. A style that sets its own fontFamily keeps it. Use this instead of `Text` from
 * react-native (biome noRestrictedImports). React 19: `ref` is an ordinary prop.
 */
export function Text({ style, ...props }: ComponentProps<typeof RNText>) {
  const flat = StyleSheet.flatten(style) ?? {};
  const font =
    flat.fontFamily || !fontState.loaded
      ? null
      : { fontFamily: fontFor(flat.fontWeight), fontWeight: "normal" as const };
  return <RNText {...props} style={font ? [style, font] : style} />;
}
