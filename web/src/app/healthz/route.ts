/** Liveness probe for the container healthcheck. No dependencies checked. */
export function GET() {
  return Response.json({ status: "ok" });
}
