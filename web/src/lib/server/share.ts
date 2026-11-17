import "server-only";

import { type ApiClient, createApiClient } from "@labtrack/shared";
import { cookies, headers } from "next/headers";

import { CLIENT_IP_HEADER, forwardedClientIp } from "@/lib/forwarded";

const API_INTERNAL_URL = process.env.API_INTERNAL_URL ?? "http://localhost:8000";

/**
 * A share link's viewing session (Phase 7.3) lives only in this httpOnly cookie (BFF): the
 * browser's JS never holds it. `__Host-` pins it to this host and path `/`; SameSite=Strict;
 * it ends with the session (30 minutes at most - the API decides).
 */
export const SHARE_COOKIE = "__Host-labtrack_share";

export async function shareSession(): Promise<string | null> {
  return (await cookies()).get(SHARE_COOKIE)?.value ?? null;
}

export async function startShareSession(session: string, expiresAt: string): Promise<void> {
  (await cookies()).set(SHARE_COOKIE, session, {
    httpOnly: true,
    secure: true,
    sameSite: "strict",
    path: "/",
    expires: new Date(expiresAt),
  });
}

/** Only in a server action or route handler (a page render cannot change cookies). */
export async function endShareSession(): Promise<void> {
  (await cookies()).set(SHARE_COOKIE, "", {
    httpOnly: true,
    secure: true,
    sameSite: "strict",
    path: "/",
    maxAge: 0,
  });
}

/** The viewer's own address, as Caddy passed it (null when missing or malformed). */
export async function viewerAddress(): Promise<string | null> {
  return forwardedClientIp((await headers()).get(CLIENT_IP_HEADER));
}

/** The API for this request: the viewing session (if any) and the viewer's own address, so
 * the API's per-address limit on PIN attempts counts the viewer, not this server. */
export async function shareApi(): Promise<ApiClient> {
  const session = await shareSession();
  const ip = await viewerAddress();
  return createApiClient(API_INTERNAL_URL, (input, init) => {
    const request = new Request(input, init);
    if (session) request.headers.set("X-Share-Session", session);
    if (ip) request.headers.set("X-Forwarded-For", ip);
    return fetch(request, { cache: "no-store" });
  });
}
