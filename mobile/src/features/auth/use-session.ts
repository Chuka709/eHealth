import { useSyncExternalStore } from "react";

import { type AuthStatus, getStatus, subscribe } from "./session-store";

/** Current auth status for navigation guards and screens. */
export function useSession(): AuthStatus {
  return useSyncExternalStore(subscribe, getStatus, getStatus);
}
