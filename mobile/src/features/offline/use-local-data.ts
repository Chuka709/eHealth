import NetInfo from "@react-native-community/netinfo";
import { onlineManager } from "@tanstack/react-query";
import { useEffect } from "react";
import { AppState } from "react-native";
import { sendWaitingUploads } from "@/features/upload/use-uploads";
import { authFetch } from "@/lib/api";
import { apiBaseUrl } from "@/lib/api-base";
import { startCachePersistence } from "@/lib/persist";
import { queryClient } from "@/lib/query-client";

import { flush, type QueuedWrite } from "./queue";

// TanStack Query pauses requests while offline and resumes them on reconnect.
onlineManager.setEventListener((setOnline) =>
  NetInfo.addEventListener((state) => {
    setOnline(state.isConnected !== false);
  }),
);

export function sendQueued(write: QueuedWrite, signal?: AbortSignal): Promise<Response> {
  return authFetch(`${apiBaseUrl}${write.path}`, {
    method: write.method,
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(write.body),
    signal,
  });
}

/**
 * Signed-in, unlocked screens only ((app)/_layout): restores the encrypted query cache and
 * sends queued writes now, when the network comes back and when the app returns to the
 * foreground. Nothing here runs while the lock screen is up or after sign-out.
 */
export function useLocalData(): void {
  useEffect(() => {
    let active = true;
    const send = () => {
      if (!active) return;
      void flush(sendQueued)
        .then((sent) => {
          if (sent > 0) {
            void queryClient.invalidateQueries({ queryKey: ["vitals"] });
            void queryClient.invalidateQueries({ queryKey: ["intakes"] });
          }
        })
        .catch(() => undefined)
        .finally(() => {
          void queryClient.invalidateQueries({ queryKey: ["queue"] });
          // lab result files (3.4): after the small writes, one file at a time
          void sendWaitingUploads();
        });
    };
    void startCachePersistence()
      .catch(() => undefined) // the app works without the offline cache
      .finally(send);
    const offNet = NetInfo.addEventListener((state) => {
      if (state.isConnected) send();
    });
    const appState = AppState.addEventListener("change", (state) => {
      if (state === "active") send();
    });
    return () => {
      active = false;
      offNet();
      appState.remove();
    };
  }, []);
}
