/**
 * The store (beta/production) configuration (Phase 2.11c): the final package, no dev launcher,
 * the blocked permissions, https only. Mods (manifest) are checked by `expo config --type
 * introspect` before a store build (docs/BETA.md).
 */
import type { ConfigContext, ExpoConfig } from "expo/config";

type Env = Record<string, string | undefined>;

function load(env: Env): ExpoConfig {
  const saved = { ...process.env };
  Object.assign(process.env, env);
  for (const [k, v] of Object.entries(env)) if (v === undefined) delete process.env[k];
  try {
    let make: ((ctx: ConfigContext) => ExpoConfig) | undefined;
    jest.isolateModules(() => {
      make = (require("../app.config") as { default: (ctx: ConfigContext) => ExpoConfig }).default;
    });
    if (!make) throw new Error("app.config did not load");
    return make({ config: {} } as ConfigContext);
  } finally {
    process.env = saved;
  }
}

const STORE: Env = {
  APP_VARIANT: "production",
  EXPO_PUBLIC_API_URL: "https://beta.example.invalid",
  EXPO_PUBLIC_SUPPORT_PHONE: "70000000",
  EXPO_PUBLIC_PRIVACY_URL: "https://example.mn/privacy",
  APP_BUNDLE_ID: undefined,
  EAS_PROJECT_ID: undefined,
};

test("the store build uses the final package and no dev launcher", () => {
  const config = load(STORE);
  expect(config.android?.package).toBe("mn.munkhly.labtrack");
  expect(config.ios?.bundleIdentifier).toBe("mn.munkhly.labtrack");
  expect(config.name).toBe("LabTrack MN");
  const plugins = (config.plugins ?? []).map((p) => (Array.isArray(p) ? p[0] : p));
  expect(plugins).not.toContain("expo-dev-client");
  expect(config.android?.blockedPermissions).toEqual(
    expect.arrayContaining([
      "android.permission.USE_EXACT_ALARM",
      "android.permission.SYSTEM_ALERT_WINDOW",
      "android.permission.RECORD_AUDIO",
    ]),
  );
  expect(config.android?.allowBackup).toBe(false);
});

test("a store build refuses a cleartext API URL", () => {
  expect(() => load({ ...STORE, EXPO_PUBLIC_API_URL: "http://192.168.1.5:8080" })).toThrow(/https/);
});

test("the EAS project id comes from the environment only", () => {
  expect(load(STORE).extra?.eas).toBeUndefined();
  const id = "00000000-0000-4000-8000-000000000000";
  expect(load({ ...STORE, EAS_PROJECT_ID: id }).extra?.eas).toEqual({ projectId: id });
});

test("development builds keep their own package beside the store app", () => {
  const config = load({ APP_VARIANT: "development", APP_BUNDLE_ID: undefined });
  expect(config.android?.package).toBe("mn.munkhly.labtrack.development");
});

test("a production build needs an https privacy policy link", () => {
  expect(() => load({ ...STORE, EXPO_PUBLIC_PRIVACY_URL: undefined })).toThrow(/PRIVACY_URL/);
  expect(() => load({ ...STORE, EXPO_PUBLIC_PRIVACY_URL: "http://example.mn" })).toThrow(
    /PRIVACY_URL/,
  );
});
