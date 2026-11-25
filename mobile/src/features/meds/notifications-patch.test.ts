import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";

/**
 * H6 (real phone, 2026.11.25): reminders rely on the expo-notifications patch that sends its
 * broadcasts in the foreground queue (patches/expo-notifications.patch). Without it, MIUI held
 * each call for seconds and a new medicine's reminder was missed. The patch only takes effect
 * when the module is built from source (Expo ships it precompiled) - both must stay in place.
 */
const mobile = join(__dirname, "..", "..", "..");

test("H6: the foreground-broadcast patch of expo-notifications is installed", () => {
  const pkg = dirname(require.resolve("expo-notifications/package.json"));
  const service = readFileSync(
    join(pkg, "android/src/main/java/expo/modules/notifications/service/NotificationsService.kt"),
    "utf8",
  );
  expect(service.match(/LabTrack patch/g)?.length).toBe(2);
});

test("H6: expo-notifications is built from source, so the patch reaches the app", () => {
  const manifest = JSON.parse(readFileSync(join(mobile, "package.json"), "utf8")) as {
    expo?: { autolinking?: { android?: { buildFromSource?: string[] } } };
  };
  expect(manifest.expo?.autolinking?.android?.buildFromSource).toContain("expo-notifications");
});
