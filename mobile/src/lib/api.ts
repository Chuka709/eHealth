import { createApiClient } from "@labtrack/shared";

import { createAuthFetch } from "@/features/auth/auth-fetch";

import { apiBaseUrl } from "./api-base";

export { apiBaseUrl, publicApi } from "./api-base";

/** fetch with the in-memory access token, refreshed single-flight (for raw requests). */
export const authFetch = createAuthFetch(apiBaseUrl);

/** Authenticated client: adds the in-memory access token and refreshes it single-flight. */
export const api = createApiClient(apiBaseUrl, authFetch);
