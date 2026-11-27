import { space } from "@labtrack/shared";
import type { ComponentRef, ReactNode, Ref } from "react";
import { ScrollView, StyleSheet } from "react-native";
import { SafeAreaView, useSafeAreaInsets } from "react-native-safe-area-context";

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
  bottomInset = true,
}: {
  children: ReactNode;
  scrollRef?: Ref<ScreenScroll>;
  testID?: string;
  /** A screen without a header (welcome, notice): keeps clear of the status bar (2.12). */
  safeTop?: boolean;
  /** Off on a tab screen: the tab bar already keeps clear of the navigation bar. */
  bottomInset?: boolean;
}) {
  const p = usePalette();
  // Android draws edge to edge: the last button stays clear of the navigation bar (real phone
  // 2026.11.27: "Хадгалах" under the 3-button bar)
  const { bottom } = useSafeAreaInsets();
  const scroll = (
    <ScrollView
      ref={scrollRef}
      testID={testID}
      contentInsetAdjustmentBehavior="automatic"
      automaticallyAdjustKeyboardInsets
      keyboardShouldPersistTaps="handled"
      style={{ backgroundColor: p.background }}
      contentContainerStyle={[
        styles.content,
        { paddingBottom: space.lg + (bottomInset ? bottom : 0) },
      ]}
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
