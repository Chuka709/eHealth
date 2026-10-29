import { QueryClient } from "@tanstack/react-query";

/**
 * One app-wide cache so signing out can drop every cached response (CLAUDE.md rule 8).
 * In memory only for now; an encrypted MMKV persister arrives with offline support (Phase 2).
 */
export const queryClient = new QueryClient({
  defaultOptions: { queries: { retry: 1, staleTime: 30_000 } },
});
