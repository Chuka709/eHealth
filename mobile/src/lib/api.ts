import { createApiClient } from "@labtrack/shared";
import { Platform } from "react-native";

// Dev default goes through Caddy (:8080). The Android emulator reaches the host at 10.0.2.2;
// a physical phone needs EXPO_PUBLIC_API_URL=http://<PC LAN IP>:8080.
const devDefault = Platform.OS === "android" ? "http://10.0.2.2:8080" : "http://localhost:8080";

export const apiBaseUrl = process.env.EXPO_PUBLIC_API_URL ?? devDefault;

// Late-bound so tests (and any fetch polyfill installed later) are picked up.
export const api = createApiClient(apiBaseUrl, (input, init) => globalThis.fetch(input, init));
