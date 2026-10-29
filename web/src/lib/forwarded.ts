import { isIP } from "node:net";

/**
 * The admin's address as Caddy saw it, to forward to the API (docs/04 §6.1: the issuing
 * admin's network is compared with where a token is used).
 *
 * Caddy trusts no upstream proxy, so it replaces X-Forwarded-For with the connecting client's
 * address; the web container is reachable only through Caddy. The last entry is therefore the
 * one Caddy wrote. Anything that is not an IP is dropped.
 */
export function forwardedClientIp(xForwardedFor: string | null): string | null {
  if (!xForwardedFor) return null;
  const last = xForwardedFor.split(",").at(-1)?.trim() ?? "";
  return isIP(last) ? last : null;
}
