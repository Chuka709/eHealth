import { useMutation } from "@tanstack/react-query";
import { useRef } from "react";

import { api } from "@/lib/api";
import { apiError } from "@/lib/use-error-text";

import { readSecure, secureKeys } from "./secure-tokens";

export interface ChangePasswordInput {
  current: string;
  next: string;
  signOutOthers: boolean;
}

/**
 * Changes the password; this session stays, others end when asked (docs/04 §1). This phone's
 * trusted-device token goes along so it alone keeps its trust (server drops the others').
 * The passwords are handed over through a ref, not as mutation variables, so they do not stay
 * in the mutation state while the screen is open; a second submit while one runs is ignored.
 */
export function useChangePassword() {
  const input = useRef<ChangePasswordInput | null>(null);
  const mutation = useMutation({
    gcTime: 0,
    mutationFn: async () => {
      const values = input.current;
      input.current = null;
      if (!values) throw new Error("no input");
      const deviceToken = await readSecure(secureKeys.device).catch(() => null);
      const { error, response } = await api.POST("/api/v1/auth/password", {
        body: {
          current_password: values.current,
          new_password: values.next,
          sign_out_other_devices: values.signOutOthers,
          device_token: deviceToken,
        },
      });
      if (!response.ok) throw apiError(error);
    },
  });
  const submit = (values: ChangePasswordInput, options?: Parameters<typeof mutation.mutate>[1]) => {
    if (mutation.isPending) return;
    input.current = values;
    mutation.mutate(undefined, options);
  };
  return { ...mutation, submit };
}
