import { space } from "@labtrack/shared";
import { useRouter } from "expo-router";
import { useState } from "react";
import { Linking, StyleSheet, View } from "react-native";
import { useTranslations } from "use-intl";

import { Button } from "@/components/button";
import { FormMessage } from "@/components/form-message";
import { NavRow } from "@/components/nav-row";
import { Screen } from "@/components/screen";
import { LoadingView, RetryView } from "@/components/state-view";
import { Paragraph } from "@/components/text";
import { useOwnProfile } from "@/features/health/record-screens";
import { CONTACTS, type Contact, useRecords } from "@/features/health/use-health";
import { useErrorText } from "@/lib/use-error-text";

/** Emergency contacts: the transplant centre first; each can be called in one tap. */
export default function ContactsScreen() {
  const t = useTranslations("app.health");
  const router = useRouter();
  const errorText = useErrorText();
  const { patients, own } = useOwnProfile();
  const [failed, setFailed] = useState<string | null>(null);
  const list = useRecords(CONTACTS as never, own?.id);
  if (patients.isPending || (own && list.isPending)) return <LoadingView />;
  if (!own || !list.data) {
    return (
      <RetryView
        text={errorText(patients.error ?? list.error)}
        onRetry={() => void list.refetch()}
      />
    );
  }
  const items = [...(list.data as Contact[])].sort(
    (a, b) => Number(b.is_transplant_center) - Number(a.is_transplant_center),
  );
  return (
    <Screen>
      {failed && <FormMessage kind="error" text={t("contact.callFailed", { phone: failed })} />}
      {items.length === 0 && <Paragraph>{t("empty")}</Paragraph>}
      {items.map((c) => (
        <View key={c.id} style={styles.group}>
          <NavRow
            label={c.name}
            hint={[c.is_transplant_center ? t("contact.centerMark") : c.relation, c.phone]
              .filter(Boolean)
              .join(" · ")}
            onPress={() => router.push(`/contacts/${c.id}` as never)}
          />
          <Button
            label={t("contact.call", { name: c.name })}
            variant="secondary"
            onPress={() =>
              void Linking.openURL(`tel:${c.phone.replace(/[^0-9+]/g, "")}`).catch(() =>
                setFailed(c.phone),
              )
            }
          />
        </View>
      ))}
      <Button label={t("contact.new")} onPress={() => router.push("/contacts/new" as never)} />
    </Screen>
  );
}

const styles = StyleSheet.create({ group: { gap: space.sm } });
