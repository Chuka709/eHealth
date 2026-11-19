import { act, fireEvent, renderRouter, screen } from "expo-router/testing-library";
import { AccessibilityInfo, AppState, type AppStateStatus } from "react-native";

import { clearAccessToken, setStatus } from "@/features/auth/session-store";
import { apiBaseUrl } from "@/lib/api-base";
import { queryClient } from "@/lib/query-client";

import { setBiometricOn, setLocked } from "./lock-store";
import { lockClock, shouldLockOnReturn } from "./use-app-lock";

const mockStore = new Map<string, string>();
/** What the biometric prompt in front of the unlock key does: ok, cancel/fail, key invalidated. */
const mockGate = { result: "ok" as "ok" | "fail" | "invalidated" | "invalidatedThrows" };

jest.mock("expo-secure-store", () => ({
  WHEN_UNLOCKED_THIS_DEVICE_ONLY: 6,
  WHEN_PASSCODE_SET_THIS_DEVICE_ONLY: 4,
  getItemAsync: jest.fn(async (key: string, options?: { requireAuthentication?: boolean }) => {
    if (options?.requireAuthentication) {
      if (mockGate.result === "fail") throw new Error("user cancel");
      if (mockGate.result === "invalidated") return null;
      if (mockGate.result === "invalidatedThrows") {
        throw new Error("android.security.keystore.KeyPermanentlyInvalidatedException");
      }
    }
    return mockStore.get(key) ?? null;
  }),
  setItemAsync: jest.fn(async (key: string, value: string) => {
    mockStore.set(key, value);
  }),
  deleteItemAsync: jest.fn(async (key: string) => {
    mockStore.delete(key);
  }),
}));
jest.mock("expo-file-system", () => ({
  Paths: { document: "doc" },
  File: class {
    exists = true;
    create() {}
    async write() {}
  },
}));
jest.mock("expo-local-authentication", () => ({
  hasHardwareAsync: jest.fn(async () => true),
  SecurityLevel: { BIOMETRIC_STRONG: 3 },
  getEnrolledLevelAsync: jest.fn(async () => 3),
}));
jest.mock("expo-screen-capture", () => ({
  preventScreenCaptureAsync: jest.fn(async () => undefined),
  enableAppSwitcherProtectionAsync: jest.fn(async () => undefined),
}));

const mockFetch = jest.fn<Promise<Response>, [Request]>();
const json = (status: number, body: unknown) =>
  new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
const given = ["terms", "privacy", "sensitive_data", "ai_processing", "cross_border"].map(
  (kind) => ({
    kind,
    current_version: "draft-2026-10",
    granted: true,
    granted_version: "draft-2026-10",
    at: "2026-10-01T00:00:00Z",
    required: ["terms", "privacy", "sensitive_data"].includes(kind),
  }),
);
const apiCalls = () => mockFetch.mock.calls.map(([r]) => r.url.slice(apiBaseUrl.length));

// Other libraries subscribe to AppState too (TanStack's focus manager): notify every listener.
const appStateListeners = new Set<(state: AppStateStatus) => void>();
jest.spyOn(AppState, "addEventListener").mockImplementation((_type, listener) => {
  const fn = listener as (state: AppStateStatus) => void;
  appStateListeners.add(fn);
  return { remove: () => appStateListeners.delete(fn) } as ReturnType<
    typeof AppState.addEventListener
  >;
});
const emitAppState = (state: AppStateStatus) => {
  for (const fn of appStateListeners) fn(state);
};

beforeEach(() => {
  queryClient.clear();
  clearAccessToken();
  setStatus("loading");
  setLocked(false);
  setBiometricOn(false);
  mockStore.clear();
  mockStore.set("lt.refresh", "r0");
  mockStore.set("lt.biometric", "on");
  mockStore.set("lt.unlock_gate", "1");
  mockGate.result = "ok";
  mockFetch.mockReset();
  mockFetch.mockImplementation(async (input: Request | string, init?: RequestInit) => {
    const request = typeof input === "string" ? new Request(input, init) : input;
    const path = request.url.slice(apiBaseUrl.length).split("?")[0];
    if (path === "/api/v1/auth/refresh") {
      return json(200, {
        access_token: "a1",
        token_type: "bearer",
        expires_in: 900,
        refresh_token: "r1",
      });
    }
    if (path === "/api/v1/me/consents") return json(200, given);
    if (path === "/api/v1/patients")
      return json(200, [
        {
          id: "00000000-0000-4000-8000-000000000001",
          relation: "self",
          access_level: "owner",
          full_name: "Бат",
          birth_date: null,
          sex: "unknown",
          is_minor: false,
          consent_required: false,
          created_at: "2026-01-01T00:00:00Z",
        },
      ]);
    if (path === "/api/v1/me/notifications") return json(200, []);
    if (path === "/api/v1/auth/logout") return new Response(null, { status: 204 });
    // the profile's records Home shows (Phase 2.9): none
    if (path.endsWith("/timezone")) {
      return json(200, { home: "Asia/Ulaanbaatar", current: "Asia/Ulaanbaatar", switches: [] });
    }
    if (/\/(transplants|medications|intakes|appointments)$/.test(path)) return json(200, []);
    return json(200, { status: "ok" });
  });
  globalThis.fetch = mockFetch as unknown as typeof fetch;
});

const app = () => renderRouter("./src/app", { initialUrl: "/" });

test("screenshots, recordings and the app-switcher snapshot are blocked app-wide", async () => {
  const ScreenCapture = jest.requireMock<Record<string, jest.Mock>>("expo-screen-capture");
  await app();
  expect(ScreenCapture.preventScreenCaptureAsync).toHaveBeenCalledWith("app");
  expect(ScreenCapture.enableAppSwitcherProtectionAsync).toHaveBeenCalled(); // jest-expo: iOS
});

test("a cold start with biometrics on opens locked and calls no API until unlocked", async () => {
  mockGate.result = "fail"; // keep the first automatic prompt from unlocking
  await app();
  expect(await screen.findByText("LabTrack MN түгжээтэй")).toBeOnTheScreen();
  expect(screen.queryByTestId("home-screen")).toBeNull();
  expect(apiCalls()).toEqual([]);

  mockGate.result = "ok";
  await fireEvent.press(screen.getByRole("button", { name: "Түгжээ тайлах" }));
  expect(await screen.findByTestId("home-screen")).toBeOnTheScreen();
});

test("the prompt is asked automatically once on open", async () => {
  await app();
  expect(await screen.findByTestId("home-screen")).toBeOnTheScreen();
});

test("a failed unlock stays locked and says what to do", async () => {
  mockGate.result = "fail";
  await app();
  expect(await screen.findByText(/Түгжээг тайлж чадсангүй/)).toBeOnTheScreen();
  expect(screen.queryByTestId("home-screen")).toBeNull();
});

test("changed biometrics invalidate the key: only a password sign-in remains", async () => {
  mockGate.result = "invalidated";
  await app();
  expect(await screen.findByText(/биометрийн тохиргоо өөрчлөгдсөн/)).toBeOnTheScreen();
  expect(screen.queryByRole("button", { name: "Түгжээ тайлах" })).toBeNull();
  await fireEvent.press(screen.getByRole("button", { name: "Гарч, нууц үгээр дахин нэвтрэх" }));
  expect(await screen.findByText("LabTrack MN-д тавтай морил")).toBeOnTheScreen();
  for (const key of ["lt.refresh", "lt.biometric", "lt.unlock_gate"]) {
    expect(mockStore.has(key)).toBe(false);
  }
});

test("with biometrics off the app opens directly", async () => {
  mockStore.set("lt.biometric", "off");
  await app();
  expect(await screen.findByTestId("home-screen")).toBeOnTheScreen();
});

describe("returning from the background", () => {
  let wall = 1_000_000;
  let mono = 50_000;
  beforeEach(() => {
    jest.spyOn(lockClock, "wall").mockImplementation(() => wall);
    jest.spyOn(lockClock, "mono").mockImplementation(() => mono);
  });
  afterEach(() => jest.restoreAllMocks());

  /** Background, then back after `wallMs` on the wall clock and `monoMs` on the steady one. */
  const away = async (wallMs: number, monoMs = wallMs) => {
    await act(() => emitAppState("background"));
    wall += wallMs;
    mono += monoMs;
    await act(() => emitAppState("active"));
  };
  const openUnlocked = async () => {
    await app();
    expect(await screen.findByTestId("home-screen")).toBeOnTheScreen();
    mockGate.result = "fail"; // keep the next lock from unlocking itself
  };

  test("under five minutes stays open", async () => {
    await openUnlocked();
    await away(60_000);
    expect(screen.getByTestId("home-screen")).toBeOnTheScreen();
  });

  test("five minutes or more locks at once, before any signed-in frame or request", async () => {
    await openUnlocked();
    mockFetch.mockClear();
    await away(5 * 60_000);
    // Synchronous: no waiting for the lock screen, and nothing was fetched on the way back.
    expect(screen.getByText("LabTrack MN түгжээтэй")).toBeOnTheScreen();
    expect(screen.queryByTestId("home-screen")).toBeNull();
    expect(apiCalls()).toEqual([]);
  });

  test("setting the wall clock back part of the way does not shorten the lock", async () => {
    await openUnlocked();
    await away(2 * 60_000, 20 * 60_000); // 20 min away, clock moved back by 18 min
    expect(screen.getByText("LabTrack MN түгжээтэй")).toBeOnTheScreen();
  });
});

test("the lock time rule: larger of wall and steady time; a wall clock going back locks", () => {
  const at = (wall: number, mono: number) => ({ wall, mono });
  expect(shouldLockOnReturn(at(0, 0), at(4 * 60_000, 4 * 60_000))).toBe(false);
  expect(shouldLockOnReturn(at(0, 0), at(5 * 60_000, 0))).toBe(true); // steady clock slept
  expect(shouldLockOnReturn(at(0, 0), at(60_000, 6 * 60_000))).toBe(true);
  expect(shouldLockOnReturn(at(10_000, 0), at(5_000, 60_000))).toBe(true);
});

test("signing out from the lock never shows a signed-in screen or calls the API", async () => {
  mockGate.result = "fail";
  await app();
  await screen.findByText("LabTrack MN түгжээтэй");
  mockFetch.mockClear();
  await fireEvent.press(screen.getByRole("button", { name: "Гарч, нууц үгээр дахин нэвтрэх" }));
  expect(await screen.findByText("LabTrack MN-д тавтай морил")).toBeOnTheScreen();
  expect(apiCalls().filter((p) => p !== "/api/v1/auth/logout")).toEqual([]);
  expect(mockStore.has("lt.refresh")).toBe(false);
});

test("an invalidated key that throws (Android) is treated as changed biometrics", async () => {
  mockGate.result = "invalidatedThrows";
  await app();
  expect(await screen.findByText(/биометрийн тохиргоо өөрчлөгдсөн/)).toBeOnTheScreen();
});

test("with a screen reader the prompt waits for the user (the heading is read first)", async () => {
  const reader = jest.spyOn(AccessibilityInfo, "isScreenReaderEnabled").mockResolvedValue(true);
  await app();
  expect(await screen.findByText("LabTrack MN түгжээтэй")).toBeOnTheScreen();
  expect(screen.queryByTestId("home-screen")).toBeNull(); // not auto-unlocked
  await fireEvent.press(screen.getByRole("button", { name: "Түгжээ тайлах" }));
  expect(await screen.findByTestId("home-screen")).toBeOnTheScreen();
  reader.mockRestore();
});
