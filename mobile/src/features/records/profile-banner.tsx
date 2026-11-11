import { fontSize, radius, space } from "@labtrack/shared";
import { StyleSheet, Text, View } from "react-native";
import { useTranslations } from "use-intl";

import { usePalette } from "@/theme/use-palette";

import { isOthers, useActiveProfile } from "./active-profile";
import { usePatients } from "./use-profile";

/**
 * On every screen that shows or writes someone else's records (H20: an entry on the wrong
 * profile): whose profile it is, in a colour, a glyph and words - never colour alone. Nothing
 * on the user's own profile, where nothing needs saying.
 */
export function ProfileBanner() {
  const t = useTranslations("app.profiles");
  const patients = usePatients();
  const active = useActiveProfile(patients.data);
  const p = usePalette();
  if (!isOthers(active, patients.data) || !active) return null;
  const tone = p.feedback.warning;
  return (
    <View
      accessible
      accessibilityRole="header"
      style={[styles.banner, { backgroundColor: tone.bg }]}
      testID="profile-banner"
    >
      <Text style={[styles.text, { color: tone.fg }]}>
        {`👤 ${t("bannerOther", { name: active.full_name })}`}
      </Text>
    </View>
  );
}

const styles = StyleSheet.create({
  banner: { borderRadius: radius.md, padding: space.md },
  text: { fontSize: fontSize.body, fontWeight: "700" },
});
