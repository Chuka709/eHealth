import { QueryClientProvider } from "@tanstack/react-query";
import { DarkTheme, DefaultTheme, Stack, ThemeProvider } from "expo-router";
import * as SplashScreen from "expo-splash-screen";
import { StatusBar } from "expo-status-bar";
import { useEffect } from "react";
import { useColorScheme } from "react-native";

import { restoreSession } from "@/features/auth/session";
import { useSession } from "@/features/auth/use-session";
import { I18nProvider } from "@/lib/i18n";
import { queryClient } from "@/lib/query-client";

// Keep the native splash until the stored session has been read (no flash of the wrong stack).
void SplashScreen.preventAutoHideAsync();

export default function RootLayout() {
  const scheme = useColorScheme();
  useEffect(() => {
    void restoreSession();
  }, []);
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
  useEffect(() => {
    if (status !== "loading") SplashScreen.hide();
  }, [status]);
  if (status === "loading") return null;
  const signedIn = status === "signedIn";
  return (
    <Stack screenOptions={{ headerShown: false }}>
      <Stack.Screen name="index" />
      <Stack.Protected guard={signedIn}>
        <Stack.Screen name="(app)" />
      </Stack.Protected>
      <Stack.Protected guard={!signedIn}>
        <Stack.Screen name="(auth)" />
      </Stack.Protected>
    </Stack>
  );
}
