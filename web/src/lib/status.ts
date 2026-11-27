import type { components } from "@labtrack/shared";

export type Readiness = components["schemas"]["Readiness"];
export type StatusKey = "ok" | "degraded" | "unreachable";

/** Maps the API readiness payload to a message key; never exposes error details. */
export function statusKey(readiness: Readiness | null): StatusKey {
  if (!readiness) return "unreachable";
  return readiness.status === "ok" && readiness.database && readiness.queue && readiness.keys
    ? "ok"
    : "degraded";
}

export async function fetchReadiness(baseUrl: string, timeoutMs = 3000): Promise<Readiness | null> {
  try {
    const res = await fetch(`${baseUrl}/api/v1/readyz`, {
      cache: "no-store",
      signal: AbortSignal.timeout(timeoutMs),
    });
    // 503 still carries a valid body describing which dependency is down.
    return (await res.json()) as Readiness;
  } catch {
    return null;
  }
}
