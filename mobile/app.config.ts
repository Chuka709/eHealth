import { mkdirSync, writeFileSync } from "node:fs";
import { join } from "node:path";
import type { ConfigContext, ExpoConfig } from "expo/config";
import {
  type ConfigPlugin,
  withAndroidManifest,
  withDangerousMod,
  withInfoPlist,
} from "expo/config-plugins";

// Bundle ID decided in 2.11 (docs/OPEN_QUESTIONS.md Q10: mn.munkhly.labtrack); it cannot
// change after release, so it comes from the environment instead of being hard-coded.
const bundleId = process.env.APP_BUNDLE_ID ?? "mn.munkhly.labtrack";
const variant = process.env.APP_VARIANT ?? "development";
const easProjectId = process.env.EAS_PROJECT_ID?.trim() || undefined;
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

// The store listing and Settings -> About link the privacy policy (docs/08 "Дэлгүүрт гаргах").
if (
  isProd &&
  !/^https:\/\/[^\s/]+\.[^\s]+$/.test(process.env.EXPO_PUBLIC_PRIVACY_URL?.trim() ?? "")
) {
  throw new Error("EXPO_PUBLIC_PRIVACY_URL must be an https:// URL for the production build");
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

// Android 12+ ignores allowBackup="false" for device-to-device transfer: without rules the
// encrypted local store (MMKV) would be copied to a new phone. It could not be read there (its
// key stays in this phone's Keystore), but nothing of it should leave: every domain is
// excluded from both cloud backup and device transfer. Replaces expo-secure-store's rules,
// which exclude only its own preferences.
// device_* are the device-protected (direct boot) storage: none written today, excluded anyway
const excludeAll = [
  "root",
  "file",
  "database",
  "sharedpref",
  "external",
  "device_root",
  "device_file",
  "device_database",
  "device_sharedpref",
]
  .map((domain) => `    <exclude domain="${domain}" path="." />`)
  .join("\n");
const NO_BACKUP_RULES = [
  '<?xml version="1.0" encoding="utf-8"?>',
  "<data-extraction-rules>",
  `  <cloud-backup>\n${excludeAll}\n  </cloud-backup>`,
  `  <device-transfer>\n${excludeAll}\n  </device-transfer>`,
  "</data-extraction-rules>",
  "",
].join("\n");
const withNoDataExtraction: ConfigPlugin = (cfg) => {
  const files = withDangerousMod(cfg, [
    "android",
    (mod) => {
      const dir = join(mod.modRequest.platformProjectRoot, "app/src/main/res/xml");
      mkdirSync(dir, { recursive: true });
      writeFileSync(join(dir, "labtrack_data_extraction_rules.xml"), NO_BACKUP_RULES);
      return mod;
    },
  ]);
  return withAndroidManifest(files, (mod) => {
    const app = mod.modResults.manifest.application?.[0];
    if (app) app.$["android:dataExtractionRules"] = "@xml/labtrack_data_extraction_rules";
    return mod;
  });
};

// Registered before the `plugins` list is applied, so its mods run after theirs.
export default (ctx: ConfigContext): ExpoConfig => {
  const config = withNoDataExtraction(appConfig(ctx));
  return isProd ? withStoreHardening(config) : config;
};

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
    // Medicine reminders on time (docs/08, H18): the user grants it on the explanation screen;
    // without it reminders still come, an hour or more late (inexact, 2.10d), and Medicines says so.
    permissions: ["android.permission.SCHEDULE_EXACT_ALARM"],
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
  // EAS project (push tokens, builds): `eas init` once on the company's Expo account, then
  // EAS_PROJECT_ID in the EAS environment. Without it the app runs and push stays off.
  ...(easProjectId ? { extra: { ...config.extra, eas: { projectId: easProjectId } } } : {}),
  experiments: { typedRoutes: true, reactCompiler: true },
});
