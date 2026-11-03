import { useState } from "react";

import { readUnlockGate } from "@/features/auth/secure-tokens";

import { disableBiometricLock, enableBiometricLock, useBiometricState } from "./biometric";
import { setLocked } from "./lock-store";

/**
 * The Settings switch. Turning the lock *off* also needs the biometric: otherwise anyone holding
 * the unlocked phone could switch the protection off. An invalidated unlock key (someone added
 * a finger or face) must not turn it off either: that is exactly when only a password sign-in
 * may follow, so the app locks and the lock screen asks for it.
 */
export function useBiometricToggle(prompt: string, disablePrompt: string) {
  const state = useBiometricState();
  const [busy, setBusy] = useState(false);
  const [failed, setFailed] = useState(false);

  const setOn = async (on: boolean) => {
    if (busy) return;
    setBusy(true);
    setFailed(false);
    try {
      if (on) {
        if (!(await enableBiometricLock(prompt))) setFailed(true);
        return;
      }
      const check = await readUnlockGate(disablePrompt);
      if (check === "ok") await disableBiometricLock();
      else if (check === "invalidated") setLocked(true);
      else setFailed(true);
    } catch {
      setFailed(true);
    } finally {
      setBusy(false);
    }
  };

  return {
    on: state.data?.choice === "on",
    available: state.data?.available === true,
    busy,
    failed,
    setOn,
  };
}
