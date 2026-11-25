import { minTouchTarget, space } from "@labtrack/shared";
import { Platform, Pressable, StyleSheet } from "react-native";

import { usePalette } from "@/theme/use-palette";

import { Icon } from "./icon";

/**
 * A screen's main "add" action in its header (UX audit #3): reachable without scrolling past a
 * long list. The full action is said to screen readers; the list's own button stays too.
 */
export function HeaderAdd({
  label,
  onPress,
  testID,
}: {
  label: string;
  onPress: () => void;
  testID?: string;
}) {
  const p = usePalette();
  const size = Platform.OS === "ios" ? minTouchTarget.ios : minTouchTarget.android;
  return (
    <Pressable
      onPress={onPress}
      accessibilityRole="button"
      accessibilityLabel={label}
      style={({ pressed }) => [
        styles.hit,
        { minWidth: size, minHeight: size, opacity: pressed ? 0.7 : 1 },
      ]}
      testID={testID}
    >
      <Icon name="plus" color={p.primary} size={28} />
    </Pressable>
  );
}

const styles = StyleSheet.create({
  hit: { alignItems: "center", justifyContent: "center", paddingHorizontal: space.xs },
});
