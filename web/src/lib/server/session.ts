import "server-only";

import { cookies } from "next/headers";

/**
 * The admin session token lives only in this httpOnly cookie (BFF): browser JS never sees it.
 * `__Host-` pins it to this host and path `/`, Secure (browsers treat http://localhost as
 * secure), SameSite=Strict so no other site can make the browser send it. The API knows the
 * name too (api/deps.py) and refuses activation tokens presented alongside it.
 */
export const ADMIN_COOKIE = "__Host-labtrack_admin";

export async function sessionToken(): Promise<string | null> {
  return (await cookies()).get(ADMIN_COOKIE)?.value ?? null;
}

export async function startSession(token: string, expiresAt: string): Promise<void> {
  (await cookies()).set(ADMIN_COOKIE, token, {
    httpOnly: true,
    secure: true,
    sameSite: "strict",
    path: "/",
    expires: new Date(expiresAt),
  });
}

export async function endSession(): Promise<void> {
  (await cookies()).delete(ADMIN_COOKIE);
}
