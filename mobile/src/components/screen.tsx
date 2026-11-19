import { space } from "@labtrack/shared";
import type { ComponentRef, ReactNode, Ref } from "react";
import { ScrollView, StyleSheet } from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";

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
  safeTop = false,
}: {
  children: ReactNode;
  scrollRef?: Ref<ScreenScroll>;
  testID?: string;
  /** A screen without a header (welcome, notice): keeps clear of the status bar (2.12). */
  safeTop?: boolean;
}) {
  const p = usePalette();
  const scroll = (
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
  return safeTop ? (
    <SafeAreaView edges={["top"]} style={{ flex: 1, backgroundColor: p.background }}>
      {scroll}
    </SafeAreaView>
  ) : (
    scroll
  );
}

const styles = StyleSheet.create({
  content: { padding: space.lg, gap: space.lg },
});
