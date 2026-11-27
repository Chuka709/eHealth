import { localStore } from "@/lib/local-store";

/**
 * "Open the emergency card while the app is locked" (docs/08, H17, H22): a choice of this
 * device, never sent to the server (PROGRESS Phase 2 decision 3). It is off by default (user
 * decision 10e). It is kept per profile, as the profile ids for which the locked app may show
 * the saved card. It holds no health data: only ids, in the encrypted local store, and it is
 * cleared with the store on sign-out.
 *
 * It matters only with the app's biometric lock on. Without that lock the card is one tap
 * away anyway. The phone's own lock screen is never covered: an app cannot draw there. The
 * wallpaper and wallet card (2.7d) are for that.
 */

const UNLOCKED_KEY = "prefs.emergency_unlocked.v1";
const OFFERED_KEY = "prefs.emergency_offered.v1";
const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/;

function ids(raw: string | undefined): string[] {
  if (!raw) return [];
  try {
    const parsed: unknown = JSON.parse(raw);
    // profile ids only (a tampered or damaged value enables nothing)
    return Array.isArray(parsed)
      ? parsed.filter((x): x is string => typeof x === "string" && UUID.test(x))
      : [];
  } catch {
    return []; // unreadable: off (fail closed)
  }
}

/** The profiles whose saved card the locked app may show (none by default). */
export async function unlockedProfiles(): Promise<string[]> {
  try {
    return ids((await localStore()).getString(UNLOCKED_KEY));
  } catch {
    return [];
  }
}

/** Only cards of profiles still in `known` may open on the locked phone. */
export async function keepUnlockedOnly(known: ReadonlySet<string>): Promise<void> {
  const store = await localStore();
  const current = ids(store.getString(UNLOCKED_KEY));
  const kept = current.filter((id) => known.has(id));
  if (kept.length !== current.length) store.set(UNLOCKED_KEY, JSON.stringify(kept));
}

export async function setCardUnlocked(patientId: string, on: boolean): Promise<void> {
  const store = await localStore();
  const current = ids(store.getString(UNLOCKED_KEY)).filter((id) => id !== patientId);
  store.set(UNLOCKED_KEY, JSON.stringify(on ? [...current, patientId] : current));
}

/** Whether the one-time offer (Home, after onboarding) was answered, either way. */
export async function cardOfferAnswered(): Promise<boolean> {
  try {
    return (await localStore()).getBoolean(OFFERED_KEY) ?? false;
  } catch {
    return true; // cannot tell: do not ask
  }
}

export async function answerCardOffer(): Promise<void> {
  (await localStore()).set(OFFERED_KEY, true);
}
