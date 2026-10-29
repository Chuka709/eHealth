import { File, Paths } from "expo-file-system";

/**
 * The app's Documents folder is removed on uninstall, the iOS Keychain is not. A missing
 * marker therefore means a fresh install whose leftover Keychain items must be dropped.
 * `cleanUp` runs before the marker is written, so a failed clean-up is retried next start.
 */
export async function onFreshInstall(cleanUp: () => Promise<void>): Promise<void> {
  const marker = new File(Paths.document, "installed");
  if (marker.exists) return;
  await cleanUp();
  marker.create();
  await marker.write("1");
}
