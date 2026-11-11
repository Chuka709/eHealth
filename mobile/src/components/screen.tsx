import { space } from "@labtrack/shared";
import type { ComponentRef, ReactNode, Ref } from "react";
import { ScrollView, StyleSheet } from "react-native";

import { usePalette } from "@/theme/use-palette";

export type ScreenScroll = ComponentRef<typeof ScrollView>;

/**
 * Scrollable screen body: grows with Dynamic Type and stays usable with the keyboard open.
 * `scrollRef` lets a multi-step screen return to the top when the step changes.
 */
export function Screen({
  children,
  scrollRef,
  testID,
}: {
  children: ReactNode;
  scrollRef?: Ref<ScreenScroll>;
  testID?: string;
}) {
  const p = usePalette();
  return (
    <ScrollView
      ref={scrollRef}
      testID={testID}
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
