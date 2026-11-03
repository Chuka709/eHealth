import { Stack } from "expo-router";
import { useTranslations } from "use-intl";

import { useSession } from "@/features/auth/use-session";

export default function AuthLayout() {
  const t = useTranslations("app.common");
  const status = useSession();
  // A notice (admin reset, report, deletion) is the only screen until the user acknowledges it.
  const notice = status === "notice";
  return (
    <Stack
      screenOptions={{
        // Each screen shows its own heading; the header only carries the back button,
        // labelled in the app language rather than the system's.
        headerTitle: "",
        headerBackTitle: t("back"),
        headerBackButtonDisplayMode: "minimal",
      }}
    >
      <Stack.Protected guard={!notice}>
        <Stack.Screen name="welcome" options={{ headerShown: false }} />
        <Stack.Screen name="activate" />
        <Stack.Screen name="login" />
        <Stack.Screen name="forgot" />
      </Stack.Protected>
      <Stack.Protected guard={notice}>
        <Stack.Screen name="notice" options={{ headerShown: false }} />
      </Stack.Protected>
    </Stack>
  );
}
