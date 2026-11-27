import { QueryClient } from "@tanstack/react-query";

/**
 * One app-wide cache so signing out can drop every cached response (CLAUDE.md rule 8).
 * In memory only for now; an encrypted MMKV persister arrives with offline support (Phase 2).
 */
export const queryClient = new QueryClient({
  defaultOptions: {
    queries: { retry: 1, staleTime: 30_000 },
    // Offline, a mutation would wait (paused) for the network with its button spinning for ever
    // (DEVICE_TEST 2026.11.27, adding a medicine): it runs at once and fails with the network
    // error instead, which the screen shows. Work that must wait for the network has its own
    // queue (doses: features/offline/queue.ts, files: features/upload/upload-queue.ts).
    mutations: { networkMode: "always" },
  },
});
