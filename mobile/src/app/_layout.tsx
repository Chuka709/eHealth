import "@/lib/intl-polyfill";
import "@/lib/perf"; // the timing starts with the app (Phase 6 DoD)

import MaterialCommunityIcons from "@expo/vector-icons/MaterialCommunityIcons";
import { colors } from "@labtrack/shared";
import { QueryClientProvider } from "@tanstack/react-query";
import { useFonts } from "expo-font";
import { DarkTheme, DefaultTheme, Stack, ThemeProvider, useRouter } from "expo-router";
import { ShareIntentProvider, useShareIntentContext } from "expo-share-intent";
import * as SplashScreen from "expo-splash-screen";
import { StatusBar } from "expo-status-bar";
import { useEffect } from "react";
import { useColorScheme } from "react-native";
import { restoreSession } from "@/features/auth/session";
import { useSession } from "@/features/auth/use-session";
import { useLocked } from "@/features/lock/lock-store";
import { enablePrivacyProtection } from "@/features/lock/privacy";
import { useAppLock } from "@/features/lock/use-app-lock";
import { I18nProvider } from "@/lib/i18n";
import { showRemindersInForeground } from "@/lib/notifications";
import { queryClient } from "@/lib/query-client";
import { fontFiles, fontState, fonts } from "@/theme/fonts";

// Headers and tab labels in the app font too.
const navFonts = {
  regular: { fontFamily: fonts.regular, fontWeight: "normal" },
  medium: { fontFamily: fonts.medium, fontWeight: "normal" },
  bold: { fontFamily: fonts.semibold, fontWeight: "normal" },
  heavy: { fontFamily: fonts.bold, fontWeight: "normal" },
} as const;
const lightTheme = {
  ...DefaultTheme,
  fonts: navFonts,
  colors: { ...DefaultTheme.colors, background: colors.light.background },
};
const darkTheme = {
  ...DarkTheme,
  fonts: navFonts,
  colors: { ...DarkTheme.colors, background: colors.dark.background },
};

// Reminders that fire while the app is open are shown too (H6).
showRemindersInForeground();

// Keep the native splash until the stored session has been read (no flash of the wrong stack).
void SplashScreen.preventAutoHideAsync();

export default function RootLayout() {
  const scheme = useColorScheme();
  useEffect(() => {
    void enablePrivacyProtection();
    void restoreSession();
  }, []);
  useAppLock();
  return (
    // files shared from other apps (Phase 3.5); cleared when the app goes to the background
    <ShareIntentProvider options={{ resetOnBackground: true }}>
      <I18nProvider>
        <QueryClientProvider client={queryClient}>
          <ThemeProvider value={scheme === "dark" ? darkTheme : lightTheme}>
            <RootNavigator />
            <StatusBar style="auto" />
          </ThemeProvider>
        </QueryClientProvider>
      </I18nProvider>
    </ShareIntentProvider>
  );
}

function RootNavigator() {
  const status = useSession();
  const locked = useLocked();
  useSharedFiles(status, locked);
  // a font that fails to load falls back to the system font: never a blank app
  // icons too, so tab and row icons do not pop in after the splash
  const [fontsLoaded, fontError] = useFonts({ ...fontFiles, ...MaterialCommunityIcons.font });
  fontState.loaded = fontError === null;
  const ready = status !== "loading" && (fontsLoaded || fontError !== null);
  useEffect(() => {
    if (ready) SplashScreen.hide();
  }, [ready]);
  if (!ready) return null;
  const signedIn = status === "signedIn";
  return (
    <Stack screenOptions={{ headerShown: false }}>
      <Stack.Screen name="index" />
      {/* Locked: the lock screen is the only signed-in screen; (app) is not even mounted. */}
      <Stack.Protected guard={signedIn && locked}>
        <Stack.Screen name="lock" options={{ gestureEnabled: false }} />
      </Stack.Protected>
      <Stack.Protected guard={signedIn && !locked}>
        <Stack.Screen name="(app)" />
      </Stack.Protected>
      <Stack.Protected guard={!signedIn}>
        <Stack.Screen name="(auth)" />
      </Stack.Protected>
    </Stack>
  );
}

/**
 * Files shared from another app (3.5): with someone signed in, the upload screen opens (it asks
 * whose result it is before adding anything); shared while nobody is signed in, they belong to
 * no account and are forgotten at once (security review 3.4 M3).
 */
function useSharedFiles(status: ReturnType<typeof useSession>, locked: boolean): void {
  const { hasShareIntent, resetShareIntent } = useShareIntentContext();
  const router = useRouter();
  useEffect(() => {
    if (!hasShareIntent || status === "loading") return;
    if (status !== "signedIn") resetShareIntent();
    else if (!locked) router.navigate("/upload");
  }, [hasShareIntent, status, locked, resetShareIntent, router]);
}
