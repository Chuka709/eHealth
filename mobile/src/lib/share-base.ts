import { apiBaseUrl } from "@/lib/api-base";

/**
 * Where a share link opens (the web viewer's `/s` page, Phase 7.3). By default the API's own
 * origin: Caddy serves the API under /api and the web pages beside it. A separate web origin is
 * set with EXPO_PUBLIC_SHARE_URL (a bare https origin outside development).
 */
export function parseShareBase(raw: string | undefined, fallback: string): string {
  const url = raw?.trim().replace(/\/+$/, "") ?? "";
  if (!url) return fallback;
  if (!/^https?:\/\/[a-z0-9.-]+(:\d+)?$/.test(url)) {
    throw new Error("EXPO_PUBLIC_SHARE_URL must be a bare origin, e.g. https://labtrack.mn");
  }
  if (!__DEV__ && !url.startsWith("https://")) {
    throw new Error("EXPO_PUBLIC_SHARE_URL must use https:// outside development");
  }
  return url;
}

export const shareBaseUrl = parseShareBase(process.env.EXPO_PUBLIC_SHARE_URL, apiBaseUrl);

/** The token rides in the fragment: it never reaches a server log, a proxy or a Referer. */
export const shareLinkUrl = (token: string) => `${shareBaseUrl}/s#${token}`;
