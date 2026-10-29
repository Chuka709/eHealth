import { space } from "@labtrack/shared";
import type { ReactNode } from "react";
import { ScrollView, StyleSheet } from "react-native";

import { usePalette } from "@/theme/use-palette";

/** Scrollable screen body: grows with Dynamic Type and stays usable with the keyboard open. */
export function Screen({ children }: { children: ReactNode }) {
  const p = usePalette();
  return (
    <ScrollView
      contentInsetAdjustmentBehavior="automatic"
      automaticallyAdjustKeyboardInsets
      keyboardShouldPersistTaps="handled"
      style={{ backgroundColor: p.background }}
      contentContainerStyle={styles.content}
    >
      {children}
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  content: { padding: space.lg, gap: space.lg },
});
