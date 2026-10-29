import { useMutation } from "@tanstack/react-query";

import { publicApi } from "@/lib/api-base";
import { apiError } from "@/lib/use-error-text";

export interface ActivateInput {
  token: string;
  username: string;
  password: string;
}

/**
 * Sets the user's own password with a one-time activation/reset token plus the username from
 * the sign-in card (a caught link alone is not enough). 204, no session.
 */
export function useActivate() {
  return useMutation({
    // Do not keep the password (mutation variables) in the cache once the call is over.
    gcTime: 0,
    mutationFn: async ({ token, username, password }: ActivateInput) => {
      const { error, response } = await publicApi.POST("/api/v1/auth/activate", {
        body: { token, username, new_password: password },
      });
      if (!response.ok) throw apiError(error);
    },
  });
}
