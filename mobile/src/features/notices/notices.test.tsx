import * as Notifications from "expo-notifications";
import { router } from "expo-router";
import { act, fireEvent, renderRouter, screen, waitFor } from "expo-router/testing-library";

import { clearAccessToken, setAccessToken, setStatus } from "@/features/auth/session-store";
import {
  registerAlertsChannel,
  registerPushToken,
  resetPushChannel,
  resetPushThrottle,
} from "@/features/push/push-token";
import { apiBaseUrl } from "@/lib/api-base";
import { queryClient } from "@/lib/query-client";

import { pushData, pushRoute } from "./push-route";

const mockStore = new Map<string, string>();
jest.mock("expo-secure-store", () => ({
  WHEN_UNLOCKED_THIS_DEVICE_ONLY: 6,
  WHEN_PASSCODE_SET_THIS_DEVICE_ONLY: 4,
  getItemAsync: jest.fn(async (key: string) => mockStore.get(key) ?? null),
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
  hasHardwareAsync: jest.fn(async () => false),
  isEnrolledAsync: jest.fn(async () => false),
  SecurityLevel: { NONE: 0, SECRET: 1, BIOMETRIC_WEAK: 2, BIOMETRIC_STRONG: 3 },
  getEnrolledLevelAsync: jest.fn(async () => 0),
  authenticateAsync: jest.fn(async () => ({ success: false })),
}));
// linked to an EAS project in this file only (elsewhere: none, so no token is ever asked for)
jest.mock("expo-constants", () => ({
  __esModule: true,
  default: { expoConfig: { extra: { eas: { projectId: "project-1" } } }, easConfig: null },
}));

type Handler = (request: Request) => Promise<Response> | Response;
const mockFetch = jest.fn<Promise<Response>, [Request]>();
const json = (status: number, body: unknown) =>
  new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });

const OWN = {
  id: "00000000-0000-4000-8000-0000000000aa",
  relation: "self",
  access_level: "owner",
  full_name: "Бат",
  birth_date: null,
  sex: "unknown",
  is_minor: false,
  consent_required: false,
  created_at: "2026-01-01T00:00:00Z",
};
const MOTHER = {
  ...OWN,
  id: "00000000-0000-4000-8000-0000000000bb",
  full_name: "Дулмаа",
  relation: "self",
  access_level: "caregiver",
};
const allGiven = ["terms", "privacy", "sensitive_data"].map((kind) => ({
  kind,
  current_version: "draft-2026-10",
  granted: true,
  granted_version: "draft-2026-10",
  at: "2026-10-01T00:00:00Z",
  required: true,
}));
const DOSE_NOTICE = {
  id: 7,
  kind: "dose_overdue",
  title_key: "notification.dose_overdue",
  patient_id: MOTHER.id,
  entity_id: "41",
  created_at: "2026-11-11T04:10:00Z",
  read_at: null,
};
const INVITE_NOTICE = {
  id: 6,
  kind: "share_invite",
  title_key: "notification.caregiver_invite",
  patient_id: MOTHER.id,
  entity_id: "inv-1",
  created_at: "2026-11-10T04:10:00Z",
  read_at: "2026-11-10T05:00:00Z",
};
let notices: Record<string, unknown>[] = [];
let recorded: string | null = null;
let reads: number[] = [];
let tokens: unknown[] = [];

const handlers: Record<string, Handler> = {
  "POST /api/v1/auth/refresh": () =>
    json(200, { access_token: "a1", token_type: "bearer", expires_in: 900, refresh_token: "r1" }),
  "GET /api/v1/me": () => json(200, { locale: "mn", display_name: "Бат Болд" }),
  "GET /api/v1/me/consents": () => json(200, allGiven),
  "GET /api/v1/me/notifications": () => json(200, notices),
  "GET /api/v1/healthz": () => json(200, { status: "ok" }),
  "GET /api/v1/patients": () => json(200, [OWN, MOTHER]),
  [`GET /api/v1/patients/${OWN.id}/transplants`]: () => json(200, []),
  [`GET /api/v1/patients/${OWN.id}/medications`]: () => json(200, []),
  [`GET /api/v1/patients/${OWN.id}/timezone`]: () =>
    json(200, { home: "Asia/Ulaanbaatar", current: "Asia/Ulaanbaatar", switches: [] }),
  [`GET /api/v1/patients/${MOTHER.id}/dose-alerts/41`]: () =>
    json(200, {
      slot_at: "2026-11-11T00:00:00Z",
      medication_id: "m1",
      medication_name: "Такролимус",
      recorded,
    }),
  "POST /api/v1/me/notifications/7/read": () => {
    reads.push(7);
    return new Response(null, { status: 204 });
  },
  "PUT /api/v1/me/push-token": async (request) => {
    tokens.push(await request.json());
    return new Response(null, { status: 204 });
  },
};

beforeEach(() => {
  queryClient.clear();
  clearAccessToken();
  setStatus("loading");
  mockStore.clear();
  mockStore.set("lt.refresh", "r0");
  mockStore.set("lt.account", "00000000-0000-4000-8000-000000000001");
  notices = [DOSE_NOTICE, INVITE_NOTICE];
  recorded = null;
  reads = [];
  tokens = [];
  resetPushThrottle();
  resetPushChannel();
  mockFetch.mockReset();
  mockFetch.mockImplementation(async (input: Request | string, init?: RequestInit) => {
    const request = typeof input === "string" ? new Request(input, init) : input;
    const path = request.url.slice(apiBaseUrl.length).split("?")[0];
    const handler = handlers[`${request.method} ${path}`];
    if (!handler) return json(404, { code: "not_found", message_key: "error.not_found" });
    return handler(request);
  });
  globalThis.fetch = mockFetch as unknown as typeof fetch;
});

afterEach(() => queryClient.clear());

test("🔔 on Home counts the unread; a dose alert opens with what is logged now", async () => {
  await renderRouter("./src/app", { initialUrl: "/" });
  await fireEvent.press(await screen.findByRole("button", { name: "Мэдэгдэл, 1 шинэ" }));
  expect(await screen.findByText(/● Шинэ · Эм уусан тэмдэглэл хараахан/)).toBeOnTheScreen();
  expect(screen.getByText("Танд асран хамгаалагчийн урилга ирлээ")).toBeOnTheScreen();
  await fireEvent.press(screen.getByTestId("notice-7"));
  expect(await screen.findByText("Профайл: Дулмаа")).toBeOnTheScreen();
  expect(screen.getByText(/^Такролимус — /)).toBeOnTheScreen();
  // never "not taken": only whether something is logged
  expect(screen.getByText(/хараахан юу ч бүртгэгдээгүй байна. Шалгана уу/)).toBeOnTheScreen();
  expect(screen.queryByText(/уугаагүй/)).toBeNull();
  await waitFor(() => expect(reads).toContain(7));
});

test("a dose logged after the alert shows as logged (the push is not taken back)", async () => {
  recorded = "taken";
  await renderRouter("./src/app", { initialUrl: "/" });
  await fireEvent.press(await screen.findByRole("button", { name: "Мэдэгдэл, 1 шинэ" }));
  await fireEvent.press(await screen.findByTestId("notice-7"));
  expect(await screen.findByText("Одоо: «уусан» гэж тэмдэглэгдсэн байна.")).toBeOnTheScreen();
});

test("a notice that is gone (access ended, a stale push) says so and shows nothing", async () => {
  await renderRouter("./src/app", { initialUrl: "/" });
  await screen.findByRole("button", { name: "Мэдэгдэл, 1 шинэ" });
  // a push for a notice this account no longer has (the list does not hold it)
  await act(() => router.push("/notifications/99"));
  expect(await screen.findByText(/байхгүй болсон/)).toBeOnTheScreen();
  expect(mockFetch.mock.calls.some(([r]) => String(r.url ?? r).includes("dose-alerts"))).toBe(
    false,
  );
});

test("a push opens a screen from its kind and id only; anything else opens the list", () => {
  expect(pushRoute(pushData({ notification_id: 7, kind: "dose_overdue" }))).toBe(
    "/notifications/7",
  );
  expect(pushRoute(pushData({ notification_id: 6, kind: "share_invite" }))).toBe(
    "/caregivers/invitations",
  );
  // a result: through its notice (which names the profile and the result - 5.5)
  expect(pushRoute(pushData({ notification_id: 5, kind: "review_ready" }))).toBe(
    "/notifications/5",
  );
  expect(pushRoute(pushData({ notification_id: 4, kind: "critical_pending" }))).toBe(
    "/notifications/4",
  );
  expect(pushRoute(pushData({ notification_id: 3, kind: "admin_reset" }))).toBe("/notifications");
  for (const junk of [
    null,
    "x",
    { notification_id: "7", kind: "dose_overdue" },
    { notification_id: 0, kind: "dose_overdue" },
    { notification_id: 7, kind: "../settings" },
    { notification_id: 1.5, kind: "dose_overdue" },
  ]) {
    expect(pushData(junk)).toBeNull();
  }
  expect(pushRoute(null)).toBe("/notifications");
});

test("the push token goes to the server for this session; without one the app carries on", async () => {
  setAccessToken("a1", 900);
  setStatus("signedIn");
  // never before the private alerts channel exists (a push would use the default channel)
  jest
    .mocked(Notifications.getExpoPushTokenAsync)
    .mockResolvedValueOnce({ type: "expo", data: "ExponentPushToken[early0123456789]" });
  expect(await registerPushToken()).toBe("unavailable");
  jest.mocked(Notifications.getExpoPushTokenAsync).mockReset();
  jest.mocked(Notifications.getExpoPushTokenAsync).mockRejectedValue(new Error("no credentials"));
  await registerAlertsChannel("LabTrack");
  // no credentials (the default): nothing is sent
  expect(await registerPushToken()).toBe("unavailable");
  expect(tokens).toEqual([]);
  // with a token: sent once, then not again within a minute
  const token = "ExponentPushToken[abcdefghij0123456789]";
  jest
    .mocked(Notifications.getExpoPushTokenAsync)
    .mockResolvedValueOnce({ type: "expo", data: token });
  expect(await registerPushToken(1_000_000)).toBe("sent");
  expect(tokens).toEqual([{ token }]);
  expect(await registerPushToken(1_030_000)).toBe("throttled");
  // notifications not allowed: never asks, never sends
  jest
    .mocked(Notifications.getPermissionsAsync)
    .mockResolvedValueOnce({ granted: false, status: "denied", canAskAgain: true } as never);
  expect(await registerPushToken(2_000_000)).toBe("unavailable");
  expect(tokens).toHaveLength(1);
});

test('a push newer than the list the app holds opens its notice, not "gone"', async () => {
  notices = [INVITE_NOTICE];
  await renderRouter("./src/app", { initialUrl: "/" });
  await fireEvent.press(await screen.findByRole("button", { name: "Мэдэгдэл" }));
  expect(await screen.findByText("Танд асран хамгаалагчийн урилга ирлээ")).toBeOnTheScreen();
  // the push arrives while the list is still fresh, and is tapped
  notices = [DOSE_NOTICE, INVITE_NOTICE];
  await act(() => router.push("/notifications/7"));
  expect(await screen.findByText("Профайл: Дулмаа")).toBeOnTheScreen();
  expect(screen.queryByText(/байхгүй болсон/)).toBeNull();
});
