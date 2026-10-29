import { redirect } from "next/navigation";
import type { NextRequest } from "next/server";

import { endSession } from "@/lib/server/session";

/** The API said the admin session is over (idle, expired, revoked): forget it and sign in. */
export async function GET(request: NextRequest) {
  // A navigation from another site must not clear the cookie (logout CSRF).
  const site = request.headers.get("sec-fetch-site");
  if (site === "same-origin" || site === "none") await endSession();
  redirect("/admin/login?expired=1");
}
