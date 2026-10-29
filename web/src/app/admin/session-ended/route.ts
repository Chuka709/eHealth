import { redirect } from "next/navigation";

import { endSession } from "@/lib/server/session";

/** The API said the admin session is over (idle, expired, revoked): forget it and sign in. */
export async function GET() {
  await endSession();
  redirect("/admin/login?expired=1");
}
