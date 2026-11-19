import { fontSize, minTouchTarget, radius, space } from "@labtrack/shared";
import { useRouter } from "expo-router";
import { useEffect, useState } from "react";
import { Alert, Platform, Pressable, StyleSheet, View } from "react-native";
import { useTranslations } from "use-intl";

import { Text } from "@/components/app-text";
import { Button } from "@/components/button";
import { FormMessage } from "@/components/form-message";
import { Screen } from "@/components/screen";
import { LoadingView, RetryView } from "@/components/state-view";
import { Paragraph, Title } from "@/components/text";
import { useRecordProfile } from "@/features/health/record-screens";
import { useDashboard, useResetCards, useSaveCards } from "@/features/home/use-dashboard";
import { useTested } from "@/features/trends/use-trends";
import { useErrorText } from "@/lib/use-error-text";
import { usePalette } from "@/theme/use-palette";

type Item = { code: string; name: string };
const MAX_CARDS = 24; // as the server and the database check

/**
 * The profile's own Home cards (Phase 6.8; docs/06 §1 "Хэрэглэгч картуудыг pin/эрэмбэлнэ"):
 * reorder, remove, add a test the profile has results of; save sends the whole list (an empty
 * list is kept as "none"); "back to the organ's cards" drops the own list. The profile's
 * writers only (a reader sees the organ's cards).
 */
export default function CardsEditor() {
  const t = useTranslations("app.home.cardsEditor");
  const errorText = useErrorText();
  const router = useRouter();
  const { own } = useRecordProfile();
  const pid = own?.id ?? "";
  const dashboard = useDashboard(own?.id);
  const tested = useTested(own?.id);
  const save = useSaveCards(pid);
  const reset = useResetCards(pid);
  const [items, setItems] = useState<Item[] | null>(null);
  const [initial, setInitial] = useState<string>("");

  useEffect(() => {
    if (items === null && dashboard.data) {
      const list = dashboard.data.cards.map((c) => ({ code: c.test_code, name: c.name_mn }));
      setItems(list);
      setInitial(list.map((i) => i.code).join(","));
    }
  }, [items, dashboard.data]);

  if (!own) return <LoadingView />;
  if (dashboard.isError && !dashboard.data) {
    return <RetryView text={errorText(dashboard.error)} onRetry={() => dashboard.refetch()} />;
  }
  if (items === null) return <LoadingView />;

  const move = (i: number, by: -1 | 1) =>
    setItems((list) => {
      if (!list) return list;
      const next = [...list];
      const [it] = next.splice(i, 1);
      next.splice(i + by, 0, it);
      return next;
    });
  const remove = (code: string) => setItems((list) => list?.filter((x) => x.code !== code) ?? []);
  const addable = (tested.data ?? []).filter((x) => !items.some((i) => i.code === x.test_code));
  const busy = save.isPending || reset.isPending;
  // saving the same list as shown is not a change (the organ's cards would become fixed)
  const dirty = items.map((i) => i.code).join(",") !== initial;
  const confirmReset = () =>
    Alert.alert(t("resetTitle"), t("resetConfirm"), [
      { text: t("cancel"), style: "cancel" },
      {
        text: t("reset"),
        style: "destructive",
        onPress: () => reset.mutate(undefined, { onSuccess: () => router.back() }),
      },
    ]);
  const error = save.error ?? reset.error;

  return (
    <Screen testID="cards-editor">
      <Paragraph muted>{t("hint")}</Paragraph>
      {items.length === 0 && <Paragraph muted>{t("empty")}</Paragraph>}
      {items.map((it, i) => (
        <View key={it.code} style={styles.row} testID={`edit-${it.code}`}>
          <Text style={styles.name}>{it.name}</Text>
          <View style={styles.actions}>
            <Small
              label={t("up")}
              a11y={t("upFor", { name: it.name })}
              disabled={i === 0}
              onPress={() => move(i, -1)}
            />
            <Small
              label={t("down")}
              a11y={t("downFor", { name: it.name })}
              disabled={i === items.length - 1}
              onPress={() => move(i, 1)}
            />
            <Small
              label={t("remove")}
              a11y={t("removeFor", { name: it.name })}
              danger
              onPress={() => remove(it.code)}
            />
          </View>
        </View>
      ))}
      {tested.isError && <FormMessage kind="error" text={t("addFailed")} />}
      {items.length >= MAX_CARDS && <Paragraph muted>{t("full", { max: MAX_CARDS })}</Paragraph>}
      {addable.length > 0 && (
        <>
          <Title>{t("addTitle")}</Title>
          {addable.map((x) => (
            <View key={x.test_code} style={styles.row}>
              <Text style={styles.name}>{x.name_mn}</Text>
              <Small
                label={t("add")}
                a11y={t("addFor", { name: x.name_mn })}
                disabled={items.length >= MAX_CARDS}
                onPress={() => setItems([...items, { code: x.test_code, name: x.name_mn }])}
              />
            </View>
          ))}
        </>
      )}
      {error && <FormMessage kind="error" text={errorText(error)} />}
      <Button
        label={t("save")}
        disabled={busy || !dirty}
        onPress={() =>
          save.mutate(
            items.map((i) => i.code),
            { onSuccess: () => router.back() },
          )
        }
      />
      <Button variant="link" label={t("reset")} disabled={busy} onPress={confirmReset} />
    </Screen>
  );
}

function Small({
  label,
  a11y,
  onPress,
  disabled = false,
  danger = false,
}: {
  label: string;
  a11y: string;
  onPress: () => void;
  disabled?: boolean;
  /** removing: the destructive tone (with its word - never colour alone) */
  danger?: boolean;
}) {
  const p = usePalette();
  const tone = disabled ? p.textMuted : danger ? p.danger : p.primary;
  return (
    <Pressable
      onPress={onPress}
      disabled={disabled}
      accessibilityRole="button"
      accessibilityLabel={a11y}
      accessibilityState={{ disabled }}
      style={[styles.small, { borderColor: disabled ? p.border : tone }]}
    >
      <Text style={[styles.smallText, { color: tone }]}>{label}</Text>
    </Pressable>
  );
}

const styles = StyleSheet.create({
  row: { gap: space.sm, paddingVertical: space.xs },
  name: { fontSize: fontSize.body, fontWeight: "600" },
  actions: { flexDirection: "row", flexWrap: "wrap", gap: space.sm },
  small: {
    minHeight: Platform.OS === "ios" ? minTouchTarget.ios : minTouchTarget.android,
    minWidth: 72,
    paddingHorizontal: space.md,
    borderRadius: radius.md,
    borderWidth: 1,
    alignItems: "center",
    justifyContent: "center",
  },
  smallText: { fontSize: fontSize.body, fontWeight: "600" },
});
