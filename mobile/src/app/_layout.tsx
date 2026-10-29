import { QueryClientProvider } from "@tanstack/react-query";
import { DarkTheme, DefaultTheme, Stack, ThemeProvider } from "expo-router";
import { StatusBar } from "expo-status-bar";
import { useEffect } from "react";
import { useColorScheme } from "react-native";

import { restoreSession } from "@/features/auth/session";
import { I18nProvider } from "@/lib/i18n";
import { queryClient } from "@/lib/query-client";

export default function RootLayout() {
  const scheme = useColorScheme();
  useEffect(() => {
    void restoreSession();
  }, []);
  return (
    <I18nProvider>
      <QueryClientProvider client={queryClient}>
        <ThemeProvider value={scheme === "dark" ? DarkTheme : DefaultTheme}>
          <Stack screenOptions={{ headerTitle: "LabTrack MN" }} />
          <StatusBar style="auto" />
        </ThemeProvider>
      </QueryClientProvider>
    </I18nProvider>
  );
}
