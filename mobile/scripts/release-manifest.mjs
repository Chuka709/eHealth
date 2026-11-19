// Release manifest check (8.4; docs/BETA.md §2): the store build's Android manifest as the config
// plugins write it (`expo config --type introspect`), checked before `eas build --profile beta`.
// Library manifests merged later by Gradle are not in it - the permission list is checked again
// on the built AAB (`aapt2 dump permissions`, docs/STORE_RELEASE.md §5).
//
//   node scripts/release-manifest.mjs            # store env from the shell, placeholders otherwise
import { execFileSync } from "node:child_process";

const STORE_ENV = {
  APP_VARIANT: "production",
  EXPO_PUBLIC_API_URL: process.env.EXPO_PUBLIC_API_URL ?? "https://beta.example.invalid",
  EXPO_PUBLIC_SUPPORT_PHONE: process.env.EXPO_PUBLIC_SUPPORT_PHONE ?? "70000000",
  EXPO_PUBLIC_PRIVACY_URL: process.env.EXPO_PUBLIC_PRIVACY_URL ?? "https://example.mn/privacy",
};
// what the app itself asks for; anything else in the generated manifest fails the check
const ALLOWED = new Set([
  "android.permission.INTERNET",
  "android.permission.SCHEDULE_EXACT_ALARM",
  "android.permission.USE_BIOMETRIC",
  "android.permission.USE_FINGERPRINT",
  "android.permission.VIBRATE",
]);
const MUST_REMOVE = [
  "android.permission.USE_EXACT_ALARM", // Play refuses it for a reminder app (CLAUDE.md)
  "android.permission.SYSTEM_ALERT_WINDOW",
  "android.permission.RECORD_AUDIO",
];

const json = execFileSync("npx", ["expo", "config", "--type", "introspect", "--json"], {
  env: { ...process.env, ...STORE_ENV, EXPO_PUBLIC_ALLOW_SCREENSHOTS: "" },
  encoding: "utf8",
  shell: process.platform === "win32", // npx is a .cmd shim on Windows
  maxBuffer: 64 * 1024 * 1024,
});
const config = JSON.parse(json);
const manifest = config._internal?.modResults?.android?.manifest?.manifest;
const failures = [];
const check = (ok, message) => {
  if (!ok) failures.push(message);
};

check(manifest, "no Android manifest in the introspected config");
const permissions = (manifest?.["uses-permission"] ?? []).map((p) => ({
  name: p.$["android:name"],
  removed: p.$["tools:node"] === "remove",
}));
for (const name of MUST_REMOVE) {
  check(
    permissions.some((p) => p.name === name && p.removed),
    `${name} is not removed (tools:node="remove")`,
  );
}
for (const p of permissions) {
  check(p.removed || ALLOWED.has(p.name), `unexpected permission ${p.name}`);
}
const app = manifest?.application?.[0]?.$ ?? {};
check(app["android:allowBackup"] === "false", "android:allowBackup is not false");
check(app["android:dataExtractionRules"], "android:dataExtractionRules is missing");
const schemes = (manifest?.application?.[0]?.activity ?? []).flatMap((a) =>
  (a["intent-filter"] ?? []).flatMap((f) => (f.data ?? []).map((d) => d.$["android:scheme"])),
);
check(!schemes.some((s) => s?.startsWith("exp+")), "a dev launcher scheme (exp+...) is present");
check(config.android?.package === "mn.munkhly.labtrack", "the package is not mn.munkhly.labtrack");
check(
  !(config.plugins ?? []).some((p) => (Array.isArray(p) ? p[0] : p) === "expo-dev-client"),
  "expo-dev-client is in a store build",
);
if (!process.env.EXPO_PUBLIC_API_URL) {
  console.warn("release-manifest: placeholder URLs (set the EAS beta env to check the real ones)");
}

if (failures.length > 0) {
  for (const f of failures) console.error(`release-manifest: FAIL ${f}`);
  process.exit(1);
}
console.log(
  `release-manifest: ok (${permissions.filter((p) => !p.removed).length} permissions, ` +
    `${permissions.filter((p) => p.removed).length} removed)`,
);
