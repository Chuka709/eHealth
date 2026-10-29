import { isIP } from "node:net";

/** Set by Caddy only ({client_ip}: overwrites any value the client sent, honours trusted_proxies). */
export const CLIENT_IP_HEADER = "x-labtrack-client-ip";

/**
 * The admin's address as Caddy determined it, to forward to the API (docs/04 §6.1: the issuing
 * admin's network is compared with where a token is used). The web container is reachable only
 * through Caddy. Anything that is not a single IP is dropped.
 */
export function forwardedClientIp(value: string | null): string | null {
  const ip = value?.trim() ?? "";
  return isIP(ip) ? ip : null;
}
