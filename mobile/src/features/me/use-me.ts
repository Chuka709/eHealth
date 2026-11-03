import type { components } from "@labtrack/shared";
import { useMutation, useQuery } from "@tanstack/react-query";
import { useEffect } from "react";

import { api } from "@/lib/api";
import { setLocale } from "@/lib/i18n";
import { queryClient } from "@/lib/query-client";
import { apiError } from "@/lib/use-error-text";

export type Me = components["schemas"]["MeOut"];
type MeUpdate = components["schemas"]["MeUpdate"];

const meKey = ["me"] as const;

const isLocale = (value: string): value is "mn" | "en" => value === "mn" || value === "en";

/** The signed-in user's profile; also applies their language to the whole app. */
export function useMe() {
  const query = useQuery({
    queryKey: meKey,
    queryFn: async () => {
      const { data, error } = await api.GET("/api/v1/me");
      if (!data) throw apiError(error);
      return data;
    },
  });
  const locale = query.data?.locale;
  useEffect(() => {
    if (locale && isLocale(locale)) setLocale(locale);
  }, [locale]);
  return query;
}

export function useUpdateMe() {
  return useMutation({
    mutationFn: async (body: MeUpdate) => {
      const { data, error } = await api.PATCH("/api/v1/me", { body });
      if (!data) throw apiError(error);
      return data;
    },
    onSuccess: (me) => {
      queryClient.setQueryData(meKey, me);
      if (isLocale(me.locale)) setLocale(me.locale);
    },
  });
}
