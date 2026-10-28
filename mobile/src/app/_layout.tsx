import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { DarkTheme, DefaultTheme, Stack, ThemeProvider } from "expo-router";
import { StatusBar } from "expo-status-bar";
import { useState } from "react";
import { useColorScheme } from "react-native";

import { I18nProvider } from "@/lib/i18n";

export default function RootLayout() {
  const scheme = useColorScheme();
  const [queryClient] = useState(
    () => new QueryClient({ defaultOptions: { queries: { retry: 1, staleTime: 30_000 } } }),
  );
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
