/**
 * Activation links: `labtrack://activate#<token>` (admin QR or SMS, docs/04 §1). The token is in
 * the fragment so it never reaches a server log; in the app it is kept in memory only and never
 * becomes part of a route, params or navigation history.
 */

// secrets.token_urlsafe(32) → 43 url-safe characters; allow some headroom, nothing else.
const LINK = /^labtrack:\/\/\/?activate\/?#([A-Za-z0-9_-]{32,128})$/;

// A link opened but not used soon (e.g. while signed in) must not prefill the form later.
const PENDING_TTL_MS = 2 * 60_000;

export function parseActivationLink(text: string): string | null {
  return LINK.exec(text.trim())?.[1] ?? null;
}

let pending: { token: string; at: number } | null = null;

/** Called by +native-intent before routing; the activate screen takes it once. */
export function setPendingActivationToken(token: string): void {
  pending = { token, at: Date.now() };
}

export function takePendingActivationToken(): string | null {
  const taken = pending;
  pending = null;
  return taken && Date.now() - taken.at <= PENDING_TTL_MS ? taken.token : null;
}

export function clearPendingActivationToken(): void {
  pending = null;
}

let handledUrl: string | null = null;

/**
 * Token from the app's linking URL, once per URL: the launch URL stays readable for the whole
 * process, and a token already used must not refill the form later.
 */
export function takeActivationTokenFromUrl(url: string | null): string | null {
  if (!url || url === handledUrl) return null;
  handledUrl = url;
  return parseActivationLink(url);
}
