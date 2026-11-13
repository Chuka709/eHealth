import { fontSize, minTouchTarget, radius, space } from "@labtrack/shared";
import { Platform, Pressable, StyleSheet, View } from "react-native";

import { usePalette } from "@/theme/use-palette";

import { Text } from "./app-text";

/**
 * A compact one-row choice (a period, an axis): radio buttons in a row, each at least the
 * touch-target height; the chosen one is filled and marked with ✓ (never colour alone).
 */
export function Segmented<T extends string>({
  label,
  options,
  value,
  labelOf,
  onSelect,
  testID,
}: {
  label: string;
  options: readonly T[];
  value: T;
  labelOf: (option: T) => string;
  onSelect: (option: T) => void;
  testID?: string;
}) {
  const p = usePalette();
  return (
    <View
      accessibilityRole="radiogroup"
      accessibilityLabel={label}
      style={styles.row}
      testID={testID}
    >
      {options.map((o) => {
        const on = o === value;
        return (
          <Pressable
            key={o}
            onPress={() => onSelect(o)}
            accessibilityRole="radio"
            accessibilityState={{ checked: on }}
            accessibilityLabel={labelOf(o)}
            style={[
              styles.item,
              { borderColor: p.primary, backgroundColor: on ? p.primary : p.surface },
            ]}
          >
            <Text
              style={[styles.text, { color: on ? p.onPrimary : p.primary }]}
              maxFontSizeMultiplier={1.6}
            >
              {on ? `✓ ${labelOf(o)}` : labelOf(o)}
            </Text>
          </Pressable>
        );
      })}
    </View>
  );
}

const styles = StyleSheet.create({
  row: { flexDirection: "row", flexWrap: "wrap", gap: space.xs },
  item: {
    flexGrow: 1,
    minHeight: Platform.OS === "ios" ? minTouchTarget.ios : minTouchTarget.android,
    borderWidth: 1,
    borderRadius: radius.md,
    paddingHorizontal: space.sm,
    alignItems: "center",
    justifyContent: "center",
  },
  text: { fontSize: fontSize.body, fontWeight: "600", textAlign: "center" },
});
