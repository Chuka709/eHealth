/**
 * Session state shared by the auth fetch, the refresh flow and the UI.
 * The access token lives only in memory (docs/08 security); it is never persisted.
 */

/** "notice": signed out behind a notice that must be read first (see notice.ts). */
export type AuthStatus = "loading" | "signedOut" | "signedIn" | "notice";

let status: AuthStatus = "loading";
let access: { token: string; expiresAt: number } | null = null;
const listeners = new Set<() => void>();

export function getStatus(): AuthStatus {
  return status;
}

export function setStatus(next: AuthStatus): void {
  if (next === status) return;
  status = next;
  for (const listener of listeners) listener();
}

export function subscribe(listener: () => void): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

/** Current access token if it is still valid for at least `marginMs`. */
export function getAccessToken(marginMs = 0): string | null {
  if (!access || access.expiresAt - Date.now() <= marginMs) return null;
  return access.token;
}

export function setAccessToken(token: string, expiresInSeconds: number): void {
  access = { token, expiresAt: Date.now() + expiresInSeconds * 1000 };
}

/** The account id (`sub`) of our own access token - read, not verified (the server does). */
export function tokenSubject(token: string | null): string | null {
  if (!token) return null;
  try {
    const payload = (token.split(".")[1] ?? "").replace(/-/g, "+").replace(/_/g, "/");
    const json = atob(payload.padEnd(Math.ceil(payload.length / 4) * 4, "="));
    const sub: unknown = JSON.parse(json).sub;
    return typeof sub === "string" && /^[0-9a-f-]{36}$/.test(sub) ? sub : null;
  } catch {
    return null;
  }
}

export function clearAccessToken(): void {
  access = null;
}
