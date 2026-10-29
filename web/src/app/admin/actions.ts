"use server";

import { redirect } from "next/navigation";

import { type ActionResult, adminApi, failure } from "@/lib/server/api";
import { endSession, sessionToken, startSession } from "@/lib/server/session";

// Server Actions: Next checks the Origin of every call; the session cookie is SameSite=Strict.
// Values from the form are passed to the API as they are - the API validates everything.

function text(form: FormData, name: string): string {
  const value = form.get(name);
  return typeof value === "string" ? value : "";
}

export async function signIn(_: ActionResult | null, form: FormData): Promise<ActionResult> {
  const api = await adminApi();
  if (await sessionToken()) {
    // signing in again (e.g. as someone else) ends the session this browser still holds
    await api.POST("/api/v1/admin/auth/logout").catch(() => undefined);
  }
  const { data, error, response } = await api.POST("/api/v1/admin/auth/login", {
    body: {
      username: text(form, "username").trim().toLowerCase(),
      password: text(form, "password"),
      totp_code: text(form, "totp_code").replace(/\s/g, ""),
    },
  });
  if (!data) return failure(error, response.status);
  await startSession(data.session_token, data.expires_at);
  // The page navigates itself: a redirect here would render the next page in this same
  // response, before the browser holds the new cookie.
  return { ok: true, data: null };
}

export async function signOut(): Promise<void> {
  try {
    const api = await adminApi();
    await api.POST("/api/v1/admin/auth/logout");
  } finally {
    await endSession();
  }
  redirect("/admin/login");
}
