import "@/lib/intl-polyfill";

import { QueryClientProvider } from "@tanstack/react-query";
import { DarkTheme, DefaultTheme, Stack, ThemeProvider } from "expo-router";
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
    <I18nProvider>
      <QueryClientProvider client={queryClient}>
        <ThemeProvider value={scheme === "dark" ? DarkTheme : DefaultTheme}>
          <RootNavigator />
          <StatusBar style="auto" />
        </ThemeProvider>
      </QueryClientProvider>
    </I18nProvider>
  );
}

function RootNavigator() {
  const status = useSession();
  const locked = useLocked();
  useEffect(() => {
    if (status !== "loading") SplashScreen.hide();
  }, [status]);
  if (status === "loading") return null;
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
