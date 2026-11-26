import { space } from "@labtrack/shared";
import { useFocusEffect, useLocalSearchParams, useNavigation, useRouter } from "expo-router";
import { useCallback, useEffect, useLayoutEffect, useRef, useState } from "react";
import { StyleSheet, View } from "react-native";
import { useTranslations } from "use-intl";
import { Button } from "@/components/button";
import { HeaderAdd } from "@/components/header-add";
import { NavRow } from "@/components/nav-row";
import { Screen, type ScreenScroll } from "@/components/screen";
import { EmptyState, LoadingView, RetryView } from "@/components/state-view";
import { Title } from "@/components/text";
import { EmergencyButton } from "@/features/emergency/emergency-button";
import { MonthSummary } from "@/features/meds/month-summary";
import { ReminderWarnings } from "@/features/meds/reminder-warnings";
import { TodayList } from "@/features/meds/today-list";
import { useRegimenText } from "@/features/meds/use-med-text";
import { useNow } from "@/features/meds/use-now";
import { useTodayDoses } from "@/features/meds/use-today";
import { isOthers, useActiveProfile } from "@/features/records/active-profile";
import { ProfileSwitcher } from "@/features/records/profile-switcher";
import { usePatients } from "@/features/records/use-profile";
import { loading, OFFLINE_ERROR } from "@/lib/query-state";
import { useErrorText } from "@/lib/use-error-text";

export default function MedsScreen() {
  const t = useTranslations("app.meds");
  const router = useRouter();
  const errorText = useErrorText();
  const regimenText = useRegimenText();
  const now = useNow();
  const patients = usePatients();
  const own = useActiveProfile(patients.data);
  const { doses, meds, zones, waitingForZone } = useTodayDoses(own?.id, now);
  const navigation = useNavigation();
  // opened from a reminder: its dose time ("at", an instant; "n" tells two taps apart) is
  // scrolled to and marked while the user stays here - taken off the route at once, so a later
  // visit to the tab opens as usual (ui review M2)
  const params = useLocalSearchParams<{ at?: string; n?: string }>();
  const [focus, setFocus] = useState<{ at: number; since: number } | null>(null);
  // biome-ignore lint/correctness/useExhaustiveDependencies: "n" re-runs it for a second tap on the same time
  useEffect(() => {
    if (!params.at || !/^\d+$/.test(params.at)) return;
    groupY.current = null;
    setFocus({ at: Number(params.at), since: Date.now() });
    router.setParams({ at: undefined, n: undefined });
  }, [params.at, params.n, router]);
  useFocusEffect(useCallback(() => () => setFocus(null), []));
  const scrollRef = useRef<ScreenScroll>(null);
  const listY = useRef<number | null>(null);
  const groupY = useRef<number | null>(null);
  // followed while the screen settles (failed doses, warnings, later times load above it)
  const scrollToFocus = useCallback(() => {
    if (focus === null || Date.now() - focus.since > SETTLE_MS) return;
    if (listY.current === null || groupY.current === null) return;
    const y = Math.max(0, listY.current + groupY.current - space.lg);
    requestAnimationFrame(() => scrollRef.current?.scrollTo({ y, animated: false }));
  }, [focus]);
  const onFocusLayout = useCallback(
    (y: number) => {
      groupY.current = y;
      scrollToFocus();
    },
    [scrollToFocus],
  );
  // "Эм нэмэх" without scrolling past today's doses (UX audit #3); the emergency card stays
  useLayoutEffect(() => {
    navigation.setOptions({
      headerRight: () => (
        <View style={styles.header}>
          <HeaderAdd
            label={t("add")}
            onPress={() => router.push("/meds/new")}
            testID="meds-add-header"
          />
          <EmergencyButton />
        </View>
      ),
    });
  }, [navigation, router, t]);

  // offline with nothing kept the queries wait ("paused"): say so instead of loading forever
  // zones too: until they come, a "local" medicine's doses are held back (H20)
  if (loading(patients) || (own && (loading(meds) || loading(zones)))) return <LoadingView />;
  if (!own || !meds.data) {
    const paused = patients.fetchStatus === "paused" || meds.fetchStatus === "paused";
    return (
      <RetryView
        text={errorText(patients.error ?? meds.error ?? (paused ? OFFLINE_ERROR : null))}
        onRetry={() => void (patients.data ? meds.refetch() : patients.refetch())}
      />
    );
  }
  const current = meds.data.filter((m) => m.is_current);
  const past = meds.data.filter((m) => !m.is_current);

  return (
    <Screen scrollRef={scrollRef}>
      <ProfileSwitcher />
      {!isOthers(own, patients.data) && <ReminderWarnings late />}
      <Title>{t("today")}</Title>
      <View
        onLayout={(e) => {
          listY.current = e.nativeEvent.layout.y;
          scrollToFocus();
        }}
      >
        <TodayList
          patientId={own.id}
          doses={doses}
          now={now.getTime()}
          waiting={waitingForZone}
          focusAt={focus?.at ?? null}
          onFocusLayout={onFocusLayout}
        />
      </View>
      <MonthSummary patientId={own.id} now={now} />

      <Title>{t("current")}</Title>
      {current.length === 0 && (
        <EmptyState
          icon="pill"
          text={t("noMeds")}
          action={{ label: t("add"), onPress: () => router.push("/meds/new") }}
        />
      )}
      {current.map((m) => (
        <NavRow
          key={m.id}
          label={m.strength ? `${m.name} ${m.strength}` : m.name}
          hint={regimenText(m.current_regimen)}
          onPress={() => router.push({ pathname: "/meds/[id]", params: { id: m.id } })}
          testID={`med-${m.id}`}
        />
      ))}
      {current.length > 0 && <Button label={t("add")} onPress={() => router.push("/meds/new")} />}

      {past.length > 0 && <Title>{t("past")}</Title>}
      {past.map((m) => (
        <NavRow
          key={m.id}
          label={m.strength ? `${m.name} ${m.strength}` : m.name}
          hint={regimenText(m.regimens.find((r) => r.voided_at === null))}
          onPress={() => router.push({ pathname: "/meds/[id]", params: { id: m.id } })}
        />
      ))}
    </Screen>
  );
}

const SETTLE_MS = 2_000;

const styles = StyleSheet.create({ header: { flexDirection: "row", alignItems: "center" } });
