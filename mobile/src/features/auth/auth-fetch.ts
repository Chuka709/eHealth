import { currentEpoch, refreshSession, wipeLocal } from "./session";
import { getAccessToken } from "./session-store";

// Endpoints that never carry the access token.
const PUBLIC_PATHS = new Set([
  "/api/v1/auth/login",
  "/api/v1/auth/activate",
  "/api/v1/auth/refresh",
  "/api/v1/auth/logout",
  "/api/v1/healthz",
]);

// 401 codes that mean "this access token is no longer good" (api/deps.py). Any other 401,
// e.g. a wrong current password on change-password, is the caller's to show: refreshing and
// replaying it would count a second failed attempt and sign the user out over a typo.
const SESSION_CODES = new Set(["auth.required", "auth.session_invalid"]);

// Refresh a little before expiry so a request does not race the 15-minute deadline.
const EARLY_REFRESH_MS = 30_000;

type Fetch = (request: Request) => Promise<Response>;

/**
 * fetch for the authenticated API client: adds `Authorization` only for our own API origin,
 * refreshes (single-flight) when the token is missing or about to expire, and retries once
 * after a session 401.
 */
export function createAuthFetch(
  baseUrl: string,
  send: Fetch = (request) => globalThis.fetch(request),
) {
  const sendAuthorized = async (request: Request, token: string) => {
    request.headers.set("Authorization", `Bearer ${token}`);
    const response = await send(request);
    // The API never redirects; following one could carry the token to another host.
    if (response.redirected) throw new TypeError("Network request failed");
    return response;
  };

  return async (input: RequestInfo | URL, init?: RequestInit): Promise<Response> => {
    const request = new Request(input, { ...init, redirect: "error" });
    const path = apiPath(request.url, baseUrl);
    // Never attach the token to another origin or to an anonymous endpoint.
    if (path === null || PUBLIC_PATHS.has(path)) return send(request);

    const retry = request.clone();
    const started = currentEpoch();
    const token = await validAccessToken();
    // the session changed while the token was being refreshed: this request is not its own
    if (currentEpoch() !== started) throw new TypeError("Network request failed");
    const first = await sendAuthorized(request, token);
    if (!(await isSessionError(first))) return first;

    // Signed out (or in as someone else) meanwhile: never replay this request on that session.
    if (currentEpoch() !== started) return first;
    // Another request may already have rotated the token while this one was in flight.
    let next = getAccessToken();
    if (next === null || next === token) {
      if ((await refreshSession()) !== "ok") return first;
      next = getAccessToken();
    }
    if (next === null || currentEpoch() !== started) return first;
    const second = await sendAuthorized(retry, next);
    // A fresh token was rejected: the session is gone (disabled account, revoked device).
    if (await isSessionError(second)) await wipeLocal("signedOut");
    return second;
  };
}

async function isSessionError(response: Response): Promise<boolean> {
  if (response.status !== 401) return false;
  const body: unknown = await response
    .clone()
    .json()
    .catch(() => null);
  const code = typeof body === "object" && body !== null && "code" in body ? body.code : null;
  return typeof code === "string" && SESSION_CODES.has(code);
}

async function validAccessToken(): Promise<string> {
  const current = getAccessToken(EARLY_REFRESH_MS);
  if (current) return current;
  const outcome = await refreshSession();
  const token = outcome === "ok" ? getAccessToken() : null;
  if (token) return token;
  // Surface "offline" as a network error so callers show their retry state; otherwise the
  // session ended and the navigation guard has already moved to sign-in.
  throw new TypeError(outcome === "offline" ? "Network request failed" : "Not signed in");
}

/** Path of `url` when it targets our API origin, else null. No URL parsing (RN's URL is partial). */
export function apiPath(url: string, baseUrl: string): string | null {
  if (!url.startsWith(`${baseUrl}/`)) return null;
  const path = url.slice(baseUrl.length).split(/[?#]/, 1)[0] ?? "";
  return path.length > 1 ? path.replace(/\/+$/, "") : path;
}
