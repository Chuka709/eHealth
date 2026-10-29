import { useMutation } from "@tanstack/react-query";
import * as Device from "expo-device";
import { Platform } from "react-native";

import { publicApi } from "@/lib/api-base";
import { apiError } from "@/lib/use-error-text";

import { readSecure, secureKeys } from "./secure-tokens";
import { establishSession } from "./session";

export interface LoginInput {
  username: string;
  password: string;
}

/** Sign in; sends the trusted-device token so this phone is not treated as unknown. */
export function useLogin() {
  return useMutation({
    // Do not keep the password (mutation variables) in the cache once the call is over.
    gcTime: 0,
    mutationFn: async ({ username, password }: LoginInput) => {
      const deviceToken = await readSecure(secureKeys.device).catch(() => null);
      const { data, error } = await publicApi.POST("/api/v1/auth/login", {
        body: {
          username,
          password,
          platform: Platform.OS === "ios" ? "ios" : "android",
          // The model ("iPhone 15"), not the user-chosen device name, which often holds a name.
          device_name: Device.modelName ?? null,
          device_token: deviceToken,
        },
      });
      if (!data) throw apiError(error);
      await establishSession(data);
    },
  });
}
