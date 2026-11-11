import { fontSize, minTouchTarget, radius, space } from "@labtrack/shared";
import { Platform, Pressable, StyleSheet, View } from "react-native";
import { Text } from "@/components/app-text";
import { Icon, type IconName } from "@/components/icon";

import { usePalette } from "@/theme/use-palette";

/**
 * A settings row that opens another screen: whole row is one button (label + hint read
 * together), › marks navigation. Our own row rather than @expo/ui ListItem, whose screen-reader
 * role is undocumented and whose List scrolls by itself (it cannot sit inside a form screen).
 */
export function NavRow({
  label,
  hint,
  onPress,
  testID,
  tone = "normal",
  a11yLabel,
  icon,
}: {
  label: string;
  hint?: string;
  onPress: () => void;
  testID?: string;
  /** "danger" for a row leading to an irreversible step (account deletion). */
  tone?: "normal" | "danger";
  /** What a screen reader says instead of the visible label (e.g. without a glyph). */
  a11yLabel?: string;
  /** A decorative icon before the label (2.12). */
  icon?: IconName;
}) {
  const p = usePalette();
  return (
    <Pressable
      onPress={onPress}
      accessibilityRole="button"
      accessibilityLabel={hint ? `${a11yLabel ?? label}. ${hint}` : (a11yLabel ?? label)}
      testID={testID}
      style={({ pressed }) => [
        styles.row,
        { backgroundColor: p.surface, borderColor: p.border, opacity: pressed ? 0.85 : 1 },
      ]}
    >
      {icon && (
        <View
          style={[
            styles.iconWrap,
            { backgroundColor: tone === "danger" ? p.feedback.error.bg : p.primarySoft },
          ]}
        >
          <Icon name={icon} color={tone === "danger" ? p.danger : p.primary} size={20} />
        </View>
      )}
      <View style={styles.text}>
        <Text style={[styles.label, { color: tone === "danger" ? p.danger : p.text }]}>
          {label}
        </Text>
        {hint && <Text style={[styles.hint, { color: p.textMuted }]}>{hint}</Text>}
      </View>
      <Icon name="chevron-right" color={p.textMuted} />
    </Pressable>
  );
}

const styles = StyleSheet.create({
  row: {
    minHeight: Platform.OS === "ios" ? minTouchTarget.ios : minTouchTarget.android,
    flexDirection: "row",
    alignItems: "center",
    gap: space.md,
    paddingHorizontal: space.md,
    paddingVertical: space.md,
    borderRadius: radius.md,
    borderWidth: StyleSheet.hairlineWidth,
  },
  text: { flex: 1, gap: space.xs },
  label: { fontSize: fontSize.body, fontWeight: "600" },
  hint: { fontSize: fontSize.caption, lineHeight: fontSize.caption * 1.4 },
  iconWrap: {
    width: 36,
    height: 36,
    borderRadius: radius.pill,
    alignItems: "center",
    justifyContent: "center",
  },
});
