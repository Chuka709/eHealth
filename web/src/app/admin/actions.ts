"use server";

import { redirect } from "next/navigation";

import { type ActionResult, adminApi, failure } from "@/lib/server/api";
import { endSession, startSession } from "@/lib/server/session";

// Server Actions: Next checks the Origin of every call; the session cookie is SameSite=Strict.
// Values from the form are passed to the API as they are - the API validates everything.

function text(form: FormData, name: string): string {
  const value = form.get(name);
  return typeof value === "string" ? value : "";
}

export async function signIn(_: ActionResult | null, form: FormData): Promise<ActionResult> {
  const api = await adminApi();
  const { data, error, response } = await api.POST("/api/v1/admin/auth/login", {
    body: {
      username: text(form, "username").trim().toLowerCase(),
      password: text(form, "password"),
      totp_code: text(form, "totp_code").replace(/\s/g, ""),
    },
  });
  if (!data) return failure(error, response.status);
  await startSession(data.session_token, data.expires_at);
  redirect("/admin/users");
}

export async function signOut(): Promise<void> {
  const api = await adminApi();
  await api.POST("/api/v1/admin/auth/logout");
  await endSession();
  redirect("/admin/login");
}
