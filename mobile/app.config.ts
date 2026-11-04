import type { ConfigContext, ExpoConfig } from "expo/config";
import { type ConfigPlugin, withAndroidManifest, withInfoPlist } from "expo/config-plugins";

// Bundle ID is decided before the first store build (docs/OPEN_QUESTIONS.md Q10); it cannot
// change after release, so it comes from the environment instead of being hard-coded.
const bundleId = process.env.APP_BUNDLE_ID ?? "mn.labtrack.app";
const variant = process.env.APP_VARIANT ?? "development";
const isProd = variant === "production";

// Release builds must never talk to the API over cleartext HTTP.
if (variant !== "development" && !process.env.EXPO_PUBLIC_API_URL?.startsWith("https://")) {
  throw new Error(`EXPO_PUBLIC_API_URL must be an https:// URL for the ${variant} build`);
}

// "Forgot password" and the admin-reset notice tell users whom to call (docs/04 §1).
// Same rule as src/lib/support.ts: digits, spaces, ( ) - and a leading +; 7–15 digits.
const supportPhone = process.env.EXPO_PUBLIC_SUPPORT_PHONE?.trim() ?? "";
const supportDigits = supportPhone.replace(/\D/g, "").length;
if (
  variant !== "development" &&
  !(/^\+?[0-9 ()-]+$/.test(supportPhone) && supportDigits >= 7 && supportDigits <= 15)
) {
  throw new Error(`EXPO_PUBLIC_SUPPORT_PHONE must be set for the ${variant} build`);
}

// Native permission prompts are shown before the JS bundle (and use-intl) loads, so they live
// here rather than in messages/*.json. Mongolian is the primary UI language.
const faceIdText = "LabTrack MN-ийг Face ID-аар түгжиж, нээхэд ашиглана.";
const cameraText = "Админы өгсөн идэвхжүүлэх QR кодыг уншихад камер ашиглана.";

// The dev client's plugins run even when expo-dev-client is left out of `plugins` (installed
// packages are auto-applied): they register the dev launcher's `exp+<slug>` URL scheme and, on
// iOS, Bonjour discovery with a local network prompt. A store build has no dev launcher, so these
// are removed, and iOS App Transport Security is pinned to HTTPS only (rule: no cleartext API).
const isDevScheme = (scheme: unknown) => typeof scheme === "string" && scheme.startsWith("exp+");
const withStoreHardening: ConfigPlugin = (cfg) => {
  const android = withAndroidManifest(cfg, (mod) => {
    for (const activity of mod.modResults.manifest.application?.[0]?.activity ?? []) {
      for (const filter of activity["intent-filter"] ?? []) {
        filter.data = filter.data?.filter((d) => !isDevScheme(d.$?.["android:scheme"]));
      }
    }
    return mod;
  });
  return withInfoPlist(android, (mod) => {
    const plist = mod.modResults;
    plist.CFBundleURLTypes = (plist.CFBundleURLTypes ?? [])
      .map((type) => ({
        ...type,
        CFBundleURLSchemes: (type.CFBundleURLSchemes ?? []).filter((s) => !isDevScheme(s)),
      }))
      .filter((type) => type.CFBundleURLSchemes.length > 0);
    delete plist.NSBonjourServices;
    delete plist.NSLocalNetworkUsageDescription;
    plist.NSAppTransportSecurity = { NSAllowsArbitraryLoads: false };
    return mod;
  });
};

// Registered before the `plugins` list is applied, so its mods run after theirs.
export default (ctx: ConfigContext): ExpoConfig =>
  isProd ? withStoreHardening(appConfig(ctx)) : appConfig(ctx);

const appConfig = ({ config }: ConfigContext): ExpoConfig => ({
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
    // Least privilege (Play photo/video policy, Data safety). The camera only scans QR codes:
    // no microphone. expo-screen-capture adds media/storage access for its screenshot listener,
    // which we do not use (it checks the permission first); files stay in app storage. Its
    // DETECT_SCREEN_CAPTURE (install-time "normal") must stay: on Android 14+ the module registers
    // a screen-capture callback unconditionally at start, which throws without it.
    // The overlay permission is for the dev menu only.
    blockedPermissions: [
      "android.permission.RECORD_AUDIO",
      "android.permission.READ_MEDIA_IMAGES",
      "android.permission.READ_MEDIA_VIDEO",
      "android.permission.READ_MEDIA_VISUAL_USER_SELECTED",
      "android.permission.READ_EXTERNAL_STORAGE",
      "android.permission.WRITE_EXTERNAL_STORAGE",
      // Google Play allows it only for alarm/calendar apps: reminders use SCHEDULE_EXACT_ALARM
      // with an explanation and an inexact fallback (docs/08, hazard H18) - never this one.
      "android.permission.USE_EXACT_ALARM",
      ...(isProd ? ["android.permission.SYSTEM_ALERT_WINDOW"] : []),
    ],
  },
  plugins: [
    "expo-router",
    // Dev launcher only outside production (it adds an exp+ URL scheme).
    ...(isProd ? [] : ["expo-dev-client"]),
    // Both plugins write NSFaceIDUsageDescription; keep the text identical.
    ["expo-secure-store", { configureAndroidBackup: true, faceIDPermission: faceIdText }],
    ["expo-local-authentication", { faceIDPermission: faceIdText }],
    [
      "expo-camera",
      {
        cameraPermission: cameraText,
        microphonePermission: false,
        recordAudioAndroid: false,
        barcodeScannerEnabled: true,
      },
    ],
    // Local medication reminders (Phase 2.5); push (caregiver alerts) in 2.8. The icon and
    // channel are set with the reminder screens.
    ["expo-notifications", { color: "#0B5FA5" }],
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
