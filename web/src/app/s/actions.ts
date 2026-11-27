"use server";

import { redirect } from "next/navigation";

import type { ActionResult } from "@/lib/server/api";
import { endShareSession, shareApi, startShareSession, viewerAddress } from "@/lib/server/share";

function text(form: FormData, name: string): string {
  const value = form.get(name);
  return typeof value === "string" ? value : "";
}

/** Opens a share link with its PIN. The token came from the URL fragment (never sent to a
 * server in a URL) and goes to the API in the body; every failure reads the same. */
export async function openShare(_: ActionResult | null, form: FormData): Promise<ActionResult> {
  // Without the viewer's own address the API would count every attempt against this server
  // (one shared limit for all viewers): refused rather than sent (production only).
  if (!(await viewerAddress()) && process.env.NODE_ENV === "production") {
    return { ok: false, code: "open_failed" };
  }
  try {
    const api = await shareApi();
    const { data, response } = await api.POST("/api/v1/share/open", {
      body: { token: text(form, "token").trim(), pin: text(form, "pin").replace(/\s/g, "") },
    });
    if (!data) {
      return { ok: false, code: response.status === 429 ? "too_many" : "open_failed" };
    }
    await startShareSession(data.session, data.expires_at);
  } catch {
    return { ok: false, code: "open_failed" }; // the API unreachable: the same answer
  }
  // the page navigates itself, once the browser holds the cookie
  return { ok: true, data: null };
}

export async function endShare(): Promise<void> {
  try {
    const api = await shareApi();
    await api.POST("/api/v1/share/close"); // the session ends on the server too
  } catch {
    // the cookie still goes; the session ends by itself within 30 minutes
  }
  await endShareSession();
  redirect("/s/ended");
}
