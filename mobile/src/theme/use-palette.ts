import { colors } from "@labtrack/shared";
import { useColorScheme } from "react-native";

export function usePalette() {
  return colors[useColorScheme() === "dark" ? "dark" : "light"];
}
