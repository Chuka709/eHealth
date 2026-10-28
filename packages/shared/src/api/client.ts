import createClient, { type Client } from "openapi-fetch";

import type { paths } from "./schema";

export type ApiClient = Client<paths>;

/** Typed API client generated from the backend OpenAPI schema (`just gen-client`). */
export function createApiClient(baseUrl: string, fetchImpl?: typeof fetch): ApiClient {
  return createClient<paths>(fetchImpl ? { baseUrl, fetch: fetchImpl } : { baseUrl });
}
