import * as ScreenCapture from "expo-screen-capture";
import { useEffect } from "react";
import { Platform } from "react-native";

/**
 * iOS: blur the app-switcher snapshot while this screen is mounted (a revealed password must not
 * end up in it). Android is covered by FLAG_SECURE from `usePreventScreenCapture`.
 * The app-wide privacy overlay comes in Phase 1.11d.
 */
export function useAppSwitcherProtection(): void {
  useEffect(() => {
    if (Platform.OS !== "ios") return;
    void ScreenCapture.enableAppSwitcherProtectionAsync().catch(() => undefined);
    return () => {
      void ScreenCapture.disableAppSwitcherProtectionAsync().catch(() => undefined);
    };
  }, []);
}
