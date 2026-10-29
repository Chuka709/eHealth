import { createApiClient } from "@labtrack/shared";
import { Platform } from "react-native";

// Dev default goes through Caddy (:8080). The Android emulator reaches the host at 10.0.2.2;
// a physical phone needs EXPO_PUBLIC_API_URL=http://<PC LAN IP>:8080.
const devDefault = Platform.OS === "android" ? "http://10.0.2.2:8080" : "http://localhost:8080";

export const apiBaseUrl = (process.env.EXPO_PUBLIC_API_URL ?? devDefault).replace(/\/+$/, "");

// A bare origin only (no path, user info, query or upper case): the auth fetch decides by
// string prefix whether a request may carry the access token.
if (!/^https?:\/\/[a-z0-9.-]+(:\d+)?$/.test(apiBaseUrl)) {
  throw new Error("EXPO_PUBLIC_API_URL must be a bare origin, e.g. https://api.example.mn");
}
if (!__DEV__ && !apiBaseUrl.startsWith("https://")) {
  throw new Error("API URL must use https:// outside development");
}

/**
 * Client without credentials: login, activate, refresh, logout and health only.
 * The refresh flow uses it so a refresh never re-enters the authenticated fetch.
 * Late-bound fetch so tests (and any fetch polyfill installed later) are picked up.
 */
export const publicApi = createApiClient(apiBaseUrl, (input, init) =>
  globalThis.fetch(input, init),
);
