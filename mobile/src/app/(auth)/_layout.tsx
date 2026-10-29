import { Stack } from "expo-router";
import { useTranslations } from "use-intl";

import { useSession } from "@/features/auth/use-session";

export default function AuthLayout() {
  const t = useTranslations("app.common");
  const status = useSession();
  // After an admin reset the notice is the only screen until the user acknowledges it.
  const adminReset = status === "adminReset";
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
      <Stack.Protected guard={!adminReset}>
        <Stack.Screen name="welcome" options={{ headerShown: false }} />
        <Stack.Screen name="activate" />
        <Stack.Screen name="login" />
        <Stack.Screen name="forgot" />
      </Stack.Protected>
      <Stack.Protected guard={adminReset}>
        <Stack.Screen name="admin-reset" options={{ headerShown: false }} />
      </Stack.Protected>
    </Stack>
  );
}
