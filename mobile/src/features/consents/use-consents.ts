import type { components } from "@labtrack/shared";
// Generated from the backend (`just gen-client`): the versions of the texts in this bundle.
import bundledVersions from "@labtrack/shared/consent-versions.json";
import { useMutation, useQuery } from "@tanstack/react-query";

import { api } from "@/lib/api";
import { dropPersistedHealthData } from "@/lib/persist";
import { queryClient } from "@/lib/query-client";
import { apiError } from "@/lib/use-error-text";

export type ConsentState = components["schemas"]["ConsentOut"];
export type ConsentItem = components["schemas"]["ConsentItem"];
export type ConsentKind = ConsentItem["kind"];

export const REQUIRED_KINDS = ["terms", "privacy", "sensitive_data"] as const;
/** AI extraction needs both (docs/04 §5): offered and withdrawn together. */
export const AI_KINDS = ["ai_processing", "cross_border"] as const;

const consentsKey = ["me", "consents"] as const;

/** The user's consent states for the text versions currently shown (server decides). */
export function useConsents() {
  return useQuery({
    queryKey: consentsKey,
    queryFn: async () => {
      const { data, error } = await api.GET("/api/v1/me/consents");
      if (!data) throw apiError(error);
      return data;
    },
  });
}

/** True while any required consent is missing for its current version. */
export function needsConsent(states: readonly ConsentState[]): boolean {
  return states.some((s) => s.required && !s.granted);
}

/**
 * True when the server asks for a newer text than this app build contains: the user would
 * read an old text and consent to a new version, so the app must be updated first.
 */
export function bundleOutdated(states: readonly ConsentState[]): boolean {
  return states.some(
    (s) =>
      s.kind in bundledVersions && s.current_version !== bundledVersions[s.kind as ConsentKind],
  );
}

/**
 * The rows to send: every required consent, the AI pair when chosen, and a withdrawal of the
 * AI pair only if it is currently given (no needless rows). The version is the one of the text
 * in this bundle - what the user actually read - never the server's.
 */
export function consentItems(states: readonly ConsentState[], ai: boolean): ConsentItem[] {
  const byKind = new Map(states.map((s) => [s.kind, s]));
  const item = (kind: ConsentKind, granted: boolean): ConsentItem => ({
    kind,
    granted,
    version: bundledVersions[kind],
  });
  const items = REQUIRED_KINDS.map((kind) => item(kind, true));
  const aiGiven = AI_KINDS.some((kind) => byKind.get(kind)?.granted === true);
  if (ai || aiGiven) items.push(...AI_KINDS.map((kind) => item(kind, ai)));
  return items;
}

export function useGiveConsents() {
  return useMutation({
    mutationFn: async (items: ConsentItem[]) => {
      const { error, response } = await api.POST("/api/v1/me/consents", { body: { items } });
      if (!response.ok) throw apiError(error);
    },
    onSuccess: (_, items) => {
      // a required consent withdrawn: no health data may stay cached (memory or disk)
      if (items.some((i) => (REQUIRED_KINDS as readonly string[]).includes(i.kind) && !i.granted)) {
        void dropPersistedHealthData();
      }
    },
    // Success, or a version that changed meanwhile: either way show the server's state.
    onSettled: () => queryClient.invalidateQueries({ queryKey: consentsKey }),
  });
}
