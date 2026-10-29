import { useTranslations } from "use-intl";

/** A failed API call: the `code` of the `{code, message_key}` body (null if it had none). */
export class ApiError extends Error {
  constructor(readonly code: string | null) {
    super(code ?? "api_error");
  }
}

/** Throws an `ApiError` carrying the body's `code`. */
export function apiError(body: unknown): ApiError {
  const code =
    typeof body === "object" && body !== null && "code" in body && typeof body.code === "string"
      ? body.code
      : null;
  return new ApiError(code);
}

/** fetch() rejects with a TypeError when the network is unreachable (RN and browsers). */
function isNetworkError(error: unknown): boolean {
  return (
    error instanceof TypeError && /network request failed|failed to fetch/i.test(error.message)
  );
}

/**
 * Maps a mutation/query error to user text: the translated `error.<code>` for API errors, a
 * connection hint for network failures, the generic error otherwise — never a raw message.
 */
export function useErrorText(): (error: unknown) => string {
  const t = useTranslations();
  return (error) => {
    if (error instanceof ApiError) {
      const key = `error.${error.code}`;
      return error.code && t.has(key) ? t(key) : t("error.internal");
    }
    return isNetworkError(error) ? t("app.common.offline") : t("error.internal");
  };
}
