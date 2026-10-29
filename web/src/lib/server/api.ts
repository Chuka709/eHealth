import "server-only";

import { type ApiClient, createApiClient } from "@labtrack/shared";
import { headers } from "next/headers";
import { redirect } from "next/navigation";

import { forwardedClientIp } from "@/lib/forwarded";
import { sessionToken } from "@/lib/server/session";

const API_INTERNAL_URL = process.env.API_INTERNAL_URL ?? "http://localhost:8000";

/** What a server action returns to the page: data, or an error code to translate. */
export type ActionResult<T = null> = { ok: true; data: T } | { ok: false; code: string };

/**
 * A typed API client for this request: the admin session as a bearer token and the admin's
 * own address as X-Forwarded-For (the API trusts it only from this container and Caddy).
 * Responses are never cached.
 */
export async function adminApi(): Promise<ApiClient> {
  const token = await sessionToken();
  const ip = forwardedClientIp((await headers()).get("x-forwarded-for"));
  return createApiClient(API_INTERNAL_URL, (input, init) => {
    const request = new Request(input, init);
    if (token) request.headers.set("Authorization", `Bearer ${token}`);
    if (ip) request.headers.set("X-Forwarded-For", ip);
    return fetch(request, { cache: "no-store" });
  });
}

type ErrorBody = { code?: unknown } | undefined;

/** Maps an API error to a code; an ended session goes back to the sign-in page. */
export async function failure(
  error: unknown,
  status: number,
): Promise<{ ok: false; code: string }> {
  const code =
    typeof (error as ErrorBody)?.code === "string"
      ? String((error as ErrorBody)?.code)
      : "internal";
  if (status === 401 && code === "admin.session_invalid") {
    // works from pages and actions alike: the route handler clears the cookie
    redirect("/admin/session-ended");
  }
  return { ok: false, code };
}
