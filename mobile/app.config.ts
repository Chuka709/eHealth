import type { ConfigContext, ExpoConfig } from "expo/config";

// Bundle ID is decided before the first store build (docs/OPEN_QUESTIONS.md Q10); it cannot
// change after release, so it comes from the environment instead of being hard-coded.
const bundleId = process.env.APP_BUNDLE_ID ?? "mn.labtrack.app";
const variant = process.env.APP_VARIANT ?? "development";
const isProd = variant === "production";

// Release builds must never talk to the API over cleartext HTTP.
if (variant !== "development" && !process.env.EXPO_PUBLIC_API_URL?.startsWith("https://")) {
  throw new Error(`EXPO_PUBLIC_API_URL must be an https:// URL for the ${variant} build`);
}

export default ({ config }: ConfigContext): ExpoConfig => ({
  ...config,
  name: isProd ? "LabTrack MN" : `LabTrack MN (${variant})`,
  slug: "labtrack",
  scheme: "labtrack",
  version: "0.1.0",
  orientation: "portrait",
  icon: "./assets/images/icon.png",
  userInterfaceStyle: "automatic",
  runtimeVersion: { policy: "fingerprint" },
  ios: {
    bundleIdentifier: isProd ? bundleId : `${bundleId}.${variant}`,
    icon: "./assets/expo.icon",
    supportsTablet: false,
    config: { usesNonExemptEncryption: false },
  },
  android: {
    package: isProd ? bundleId : `${bundleId}.${variant}`,
    adaptiveIcon: {
      backgroundColor: "#E6F4FE",
      foregroundImage: "./assets/images/android-icon-foreground.png",
      backgroundImage: "./assets/images/android-icon-background.png",
      monochromeImage: "./assets/images/android-icon-monochrome.png",
    },
    // PHI must not end up in Android cloud backups.
    allowBackup: false,
    predictiveBackGestureEnabled: false,
  },
  plugins: [
    "expo-router",
    [
      "expo-splash-screen",
      {
        backgroundColor: "#0B5FA5",
        image: "./assets/images/splash-icon.png",
        imageWidth: 76,
      },
    ],
  ],
  experiments: { typedRoutes: true, reactCompiler: true },
});
