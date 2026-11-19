import MaterialCommunityIcons from "@expo/vector-icons/MaterialCommunityIcons";
import type { ComponentProps } from "react";

export type IconName = ComponentProps<typeof MaterialCommunityIcons>["name"];

/**
 * A decorative icon (2.12: replaces emoji glyphs). Never the only carrier of meaning: the
 * control next to it has a text label, so screen readers skip the icon.
 */
export function Icon({ name, color, size = 24 }: { name: IconName; color: string; size?: number }) {
  return (
    <MaterialCommunityIcons
      name={name}
      color={color}
      size={size}
      accessible={false}
      importantForAccessibility="no-hide-descendants"
      accessibilityElementsHidden
    />
  );
}
