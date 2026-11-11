import { fontSize } from "@labtrack/shared";
import type { ReactNode } from "react";
import { StyleSheet } from "react-native";
import { Text } from "@/components/app-text";

import { usePalette } from "@/theme/use-palette";

export function Title({ children }: { children: ReactNode }) {
  const p = usePalette();
  return (
    <Text accessibilityRole="header" style={[styles.title, { color: p.text }]}>
      {children}
    </Text>
  );
}

export function Paragraph({ children, muted = false }: { children: ReactNode; muted?: boolean }) {
  const p = usePalette();
  return <Text style={[styles.body, { color: muted ? p.textMuted : p.text }]}>{children}</Text>;
}

const styles = StyleSheet.create({
  title: { fontSize: fontSize.title, fontWeight: "700", letterSpacing: -0.2 },
  body: { fontSize: fontSize.body, lineHeight: fontSize.body * 1.4 },
});
