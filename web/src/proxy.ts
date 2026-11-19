import { type NextRequest, NextResponse } from "next/server";

const ADMIN_COOKIE = "__Host-labtrack_admin";

/**
 * /admin, /s (a share link's viewer, 7.3; no session check there - the API decides) and the
 * legal pages (8.1):
 * a strict, per-request nonce CSP (no inline script without the nonce, nothing from
 * other origins) and a redirect to sign-in without a session cookie. Whether the session is
 * still valid is decided by the API on every call; this only avoids rendering an empty shell.
 */
export function proxy(request: NextRequest) {
  const { pathname } = request.nextUrl;
  const admin = pathname.startsWith("/admin");
  if (admin && pathname !== "/admin/login" && !request.cookies.has(ADMIN_COOKIE)) {
    return NextResponse.redirect(new URL("/admin/login", request.url));
  }

  const nonce = Buffer.from(crypto.randomUUID()).toString("base64");
  const isDev = process.env.NODE_ENV === "development";
  const csp = [
    "default-src 'self'",
    `script-src 'self' 'nonce-${nonce}' 'strict-dynamic'${isDev ? " 'unsafe-eval'" : ""}`,
    `style-src 'self' ${isDev ? "'unsafe-inline'" : `'nonce-${nonce}'`}`,
    "img-src 'self' data:",
    "font-src 'self'",
    "connect-src 'self'",
    "object-src 'none'",
    "base-uri 'self'",
    "form-action 'self'",
    "frame-ancestors 'none'",
  ].join("; ");

  const requestHeaders = new Headers(request.headers);
  requestHeaders.set("x-nonce", nonce);
  requestHeaders.set("Content-Security-Policy", csp);
  const response = NextResponse.next({ request: { headers: requestHeaders } });
  response.headers.set("Content-Security-Policy", csp);
  response.headers.set("Cache-Control", "no-store");
  return response;
}

export const config = {
  // no prefetch exemption: every /admin and /s response carries the CSP (and /admin the
  // session check)
  matcher: ["/admin/:path*", "/s", "/s/:path*", "/privacy", "/terms", "/account-deletion"],
};
