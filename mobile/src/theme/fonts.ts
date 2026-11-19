import {
  GolosText_400Regular,
  GolosText_500Medium,
  GolosText_600SemiBold,
  GolosText_700Bold,
} from "@expo-google-fonts/golos-text";
import type { TextStyle } from "react-native";

/**
 * Golos Text (2.12 design): drawn for Cyrillic legibility, open shapes at small sizes. One
 * family; Android needs a file per weight, so the weight picks the family (`fontFor`).
 * Sizes still follow the OS font scale (Dynamic Type).
 */
export const fontFiles = {
  GolosText_400Regular,
  GolosText_500Medium,
  GolosText_600SemiBold,
  GolosText_700Bold,
};

export const fonts = {
  regular: "GolosText_400Regular",
  medium: "GolosText_500Medium",
  semibold: "GolosText_600SemiBold",
  bold: "GolosText_700Bold",
} as const;

/** False when the app font failed to load: Text keeps the system font and its own weight. */
export const fontState = { loaded: true };

/** The family for a weight; the weight itself is dropped (the file carries it). */
export function fontFor(weight: TextStyle["fontWeight"]): string {
  switch (String(weight ?? "400")) {
    case "500":
    case "medium":
      return fonts.medium;
    case "600":
    case "semibold":
      return fonts.semibold;
    case "700":
    case "800":
    case "900":
    case "bold":
    case "heavy":
    case "black":
      return fonts.bold;
    default:
      return fonts.regular;
  }
}
