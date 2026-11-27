import { getShareExtensionKey } from "expo-share-intent";

import { setPendingActivationToken } from "./activation-link";
import { getStatus } from "./session-store";

const ACTIVATE = /^(?:labtrack:\/\/\/?|\/)?activate\/?$/;
const TOKEN = /^[A-Za-z0-9_-]{32,128}$/;

/**
 * Rewrites an incoming system URL before Expo Router sees it. The only external link the app
 * accepts is the activation link (and a share from another app, which opens the upload
 * screen): its token is moved out of the URL into memory, so routes,
 * params, history and logs only ever see `/activate`. Every other link opens the app at "/"
 * (no deep links into screens, no spoofed query params such as `?activated=1`).
 * Must never throw (it runs outside the React tree).
 */
export function redirectSystemPath({ path }: { path: string; initial: boolean }): string {
  try {
    // a PDF or picture shared from another app (Messenger, Viber, Mail - Phase 3.5): the files
    // are read from expo-share-intent on the upload screen, never from this URL
    if (path.includes(`dataUrl=${getShareExtensionKey()}`)) {
      return getStatus() === "signedIn" ? "/upload" : "/";
    }
    const hash = path.indexOf("#");
    const base = hash === -1 ? path : path.slice(0, hash);
    if (!ACTIVATE.test(base)) return "/";
    const token = hash === -1 ? "" : path.slice(hash + 1);
    // Signed-in users cannot open /activate; do not keep a token around for later.
    if (TOKEN.test(token) && getStatus() !== "signedIn") setPendingActivationToken(token);
    return "/activate";
  } catch {
    return "/";
  }
}
