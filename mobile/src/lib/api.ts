import { createApiClient } from "@labtrack/shared";

import { createAuthFetch } from "@/features/auth/auth-fetch";

import { apiBaseUrl } from "./api-base";

export { apiBaseUrl, publicApi } from "./api-base";

/** Authenticated client: adds the in-memory access token and refreshes it single-flight. */
export const api = createApiClient(apiBaseUrl, createAuthFetch(apiBaseUrl));
