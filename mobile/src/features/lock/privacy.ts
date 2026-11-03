import * as ScreenCapture from "expo-screen-capture";
import { Platform } from "react-native";

/**
 * App-wide, for the whole process (decided in the 1.11 plan): no screenshots or recordings of
 * health data, and nothing readable in the app switcher. Android: FLAG_SECURE, which also blanks
 * the recents preview. iOS: screenshot/recording block (iOS 13+) plus a blur over the app
 * switcher snapshot. Best effort: a platform without support must not stop the app.
 */
export async function enablePrivacyProtection(): Promise<void> {
  try {
    await ScreenCapture.preventScreenCaptureAsync("app");
    if (Platform.OS === "ios") await ScreenCapture.enableAppSwitcherProtectionAsync();
  } catch {
    // Unsupported here; nothing else to do.
  }
}
