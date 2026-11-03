import { Host, Switch } from "@expo/ui";
import { fontSize, radius, space } from "@labtrack/shared";
import { useState } from "react";
import { StyleSheet, Text, View } from "react-native";
import { useTranslations } from "use-intl";

import { Button } from "@/components/button";
import { FormMessage } from "@/components/form-message";
import { Paragraph } from "@/components/text";
import { usePalette } from "@/theme/use-palette";

interface ConsentCardProps {
  /** Message key under app.consent (terms | privacy | sensitive_data | ai). */
  textKey: "terms" | "privacy" | "sensitive_data" | "ai";
  required: boolean;
  value: boolean;
  onChange: (value: boolean) => void;
  /** Required but not given when the user tried to continue. */
  missing?: boolean;
}

/** One consent: title (the switch label), summary, full text on demand, required/optional tag. */
export function ConsentCard({ textKey, required, value, onChange, missing }: ConsentCardProps) {
  const t = useTranslations("app.consent");
  const p = usePalette();
  const [open, setOpen] = useState(false);
  return (
    <View style={[styles.card, { backgroundColor: p.surface, borderColor: p.border }]}>
      {/* Spoken as part of the switch label below, so hidden from screen readers here. */}
      <Text
        importantForAccessibility="no"
        accessibilityElementsHidden
        style={[styles.tag, { color: p.text }]}
      >
        {required ? t("required") : t("optional")}
      </Text>
      <Host matchContents={{ vertical: true }} style={styles.switchHost}>
        <Switch
          label={`${t(`${textKey}.title`)} (${required ? t("required") : t("optional")})`}
          value={value}
          onValueChange={onChange}
          testID={`consent-${textKey}`}
        />
      </Host>
      {missing && <FormMessage kind="error" text={t("missingOne")} />}
      <Paragraph>{t(`${textKey}.summary`)}</Paragraph>
      {open && <Paragraph muted>{t(`${textKey}.body`)}</Paragraph>}
      <Button
        variant="link"
        expanded={open}
        label={open ? t("readLess") : t("readMore")}
        accessibilityLabel={`${open ? t("readLess") : t("readMore")}: ${t(`${textKey}.title`)}`}
        onPress={() => setOpen((v) => !v)}
      />
    </View>
  );
}

const styles = StyleSheet.create({
  card: {
    gap: space.sm,
    padding: space.md,
    borderRadius: radius.md,
    borderWidth: StyleSheet.hairlineWidth * 2,
  },
  tag: { fontSize: fontSize.caption, fontWeight: "600" },
  switchHost: { width: "100%" },
});
