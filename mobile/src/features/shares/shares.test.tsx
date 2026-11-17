import { fireEvent, renderRouter, screen, waitFor } from "expo-router/testing-library";
import { Alert } from "react-native";

import { clearAccessToken, setStatus } from "@/features/auth/session-store";
import { noticeKey } from "@/features/notices/notice-text";
import { resetActiveProfile, setActiveProfile } from "@/features/records/active-profile";
import { apiBaseUrl } from "@/lib/api-base";
import { queryClient } from "@/lib/query-client";

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
// a profile shared with this user as a doctor
const PATIENT = {
  ...OWN,
  id: "00000000-0000-4000-8000-0000000000cc",
  full_name: "Дорж",
  access_level: "doctor",
};
const allGiven = ["terms", "privacy", "sensitive_data"].map((kind) => ({
  kind,
  current_version: "draft-2026-10",
  granted: true,
  granted_version: "draft-2026-10",
  at: "2026-10-01T00:00:00Z",
  required: true,
}));

let posts: { path: string; body: unknown }[] = [];
const record =
  (path: string, status = 204) =>
  async (request: Request) => {
    posts.push({ path, body: await request.json().catch(() => null) });
    return new Response(null, { status });
  };

const handlers: Record<string, Handler> = {
  "POST /api/v1/auth/refresh": () =>
    json(200, { access_token: "a1", token_type: "bearer", expires_in: 900, refresh_token: "r1" }),
  "GET /api/v1/me": () => json(200, { locale: "mn", display_name: "Бат Болд" }),
  "GET /api/v1/me/consents": () => json(200, allGiven),
  "GET /api/v1/me/notifications": () => json(200, []),
  "GET /api/v1/healthz": () => json(200, { status: "ok" }),
  "GET /api/v1/patients": () => json(200, [OWN, PATIENT]),
  "GET /api/v1/me/caregiver-invitations": () => json(200, []),
  "GET /api/v1/me/share-invitations": () =>
    json(200, [
      {
        id: "sinv-1",
        inviter_name: "Оюун",
        level: "doctor",
        access_days: 7,
        created_at: "2026-11-10T00:00:00Z",
        expires_at: "2026-11-24T00:00:00Z",
      },
    ]),
  "POST /api/v1/me/share-invitations/respond": record("respond"),
  "POST /api/v1/me/shares/leave": record("leave"),
  [`GET /api/v1/patients/${OWN.id}/shares`]: () =>
    json(200, {
      shares: [
        {
          user_id: "u-9",
          display_name: "Д. Ганбат",
          level: "doctor",
          since: "2026-11-01T00:00:00Z",
          expires_at: null,
          last_viewed_at: "2026-11-15T02:30:00Z",
        },
      ],
      invitations: [
        {
          id: "i-1",
          username: "nurse.b",
          level: "viewer",
          access_days: 1,
          created_at: "2026-11-16T00:00:00Z",
          expires_at: "2026-11-30T00:00:00Z",
        },
      ],
    }),
  [`GET /api/v1/patients/${OWN.id}/share-views`]: () =>
    json(200, [
      {
        user_id: "u-9",
        display_name: "Д. Ганбат",
        day: "2026-11-15",
        first_at: "2026-11-15T01:00:00Z",
        last_at: "2026-11-15T02:30:00Z",
      },
    ]),
  [`POST /api/v1/patients/${OWN.id}/share-invitations`]: record("invite", 202),
  [`DELETE /api/v1/patients/${OWN.id}/shares/u-9`]: record("end"),
};
for (const p of [OWN, PATIENT]) {
  const base = `/api/v1/patients/${p.id}`;
  handlers[`GET ${base}/transplants`] = () => json(200, []);
  handlers[`GET ${base}/medications`] = () => json(200, []);
  handlers[`GET ${base}/timezone`] = () =>
    json(200, { home: "Asia/Ulaanbaatar", current: "Asia/Ulaanbaatar", switches: [] });
  for (const kind of ["events", "contacts", "appointments", "questions", "vitals", "allergies"]) {
    handlers[`GET ${base}/${kind}`] = () => json(200, []);
  }
}

// confirmations: answered with the non-cancel button; what was asked is kept
let asked: string[] = [];
beforeEach(() => {
  queryClient.clear();
  clearAccessToken();
  setStatus("loading");
  resetActiveProfile();
  mockStore.clear();
  mockStore.set("lt.refresh", "r0");
  mockStore.set("lt.account", "00000000-0000-4000-8000-000000000001");
  posts = [];
  asked = [];
  jest.spyOn(Alert, "alert").mockImplementation((title, message, buttons) => {
    asked.push(`${title}|${message ?? ""}`);
    buttons?.find((b) => b.style !== "cancel")?.onPress?.();
  });
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

afterEach(() => {
  queryClient.clear();
  jest.restoreAllMocks();
});

async function openTab(name: RegExp) {
  await renderRouter("./src/app", { initialUrl: "/" });
  await fireEvent.press(await screen.findByRole("button", { name }));
}

test("the owner sees who has the profile, who opened it, and invites for a chosen time", async () => {
  await openTab(/^Профайл,/);
  await fireEvent.press(await screen.findByTestId("profile-shares"));
  expect(await screen.findAllByText("Д. Ганбат")).not.toHaveLength(0);
  expect(screen.getAllByText("Цуцлах хүртэл").length).toBeGreaterThan(1); // the card and the choice
  expect(screen.getByText(/^Сүүлд нээсэн: /)).toBeOnTheScreen();
  expect(await screen.findByText(/^Д\. Ганбат — /)).toBeOnTheScreen(); // a day it was opened
  expect(screen.getByText("Үзэгч · 24 цаг")).toBeOnTheScreen(); // the open invitation
  await fireEvent.changeText(screen.getByTestId("share-username"), " Dr.Bold ");
  await fireEvent.press(screen.getByRole("radio", { name: "Үзэгч" }));
  await fireEvent.press(screen.getByRole("radio", { name: "30 хоног" }));
  await fireEvent.press(screen.getByRole("button", { name: "Урих" }));
  expect(asked[0]).toMatch(/«dr.bold»-г Үзэгч эрхээр, 30 хоног хугацаатай/);
  await waitFor(() =>
    expect(posts).toContainEqual({
      path: "invite",
      body: { username: "dr.bold", level: "viewer", days: 30 },
    }),
  );
  expect(await screen.findByText(/Хүсэлтийг хүлээн авлаа/)).toBeOnTheScreen();
});

test("the owner revokes an access after confirming", async () => {
  await openTab(/^Профайл,/);
  await fireEvent.press(await screen.findByTestId("profile-shares"));
  await fireEvent.press(
    await screen.findByRole("button", { name: "Д. Ганбат-ийн эрхийг цуцлах уу?" }),
  );
  expect(asked[0]).toMatch(/буцаах боломжгүй/);
  await waitFor(() => expect(posts.map((p) => p.path)).toContain("end"));
});

test("an invited doctor sees who asks, as what and for how long, and accepts knowingly", async () => {
  await openTab(/^Тохиргоо,/);
  await fireEvent.press(await screen.findByTestId("settings-invitations"));
  expect(await screen.findByText("Оюун таныг Эмч эрхээр урьж байна")).toBeOnTheScreen();
  expect(screen.getByText("7 хоног")).toBeOnTheScreen();
  await fireEvent.press(screen.getByRole("button", { name: "Урилгыг зөвшөөрөх — Оюун" }));
  expect(asked[0]).toMatch(/нээсэн өдрүүд профайлын эзэнд харагдана/);
  await waitFor(() =>
    expect(posts).toContainEqual({
      path: "respond",
      body: { invitation_id: "sinv-1", accept: true },
    }),
  );
});

test("a doctor can step back from a shared profile, and cannot manage its sharing", async () => {
  setActiveProfile(PATIENT.id);
  await openTab(/^Профайл,/);
  await screen.findByTestId("profile-leave-share");
  expect(screen.queryByTestId("profile-shares")).toBeNull();
  await fireEvent.press(screen.getByTestId("profile-leave-share"));
  expect(asked[0]).toMatch(/шинээр урилга хүсэх/);
  await waitFor(() =>
    expect(posts).toContainEqual({ path: "leave", body: { patient_id: PATIENT.id } }),
  );
});

test("a doctor's or a viewer's invitation reads as such in the notices", () => {
  expect(noticeKey({ kind: "share_invite", title_key: "notification.share_invite" })).toBe(
    "kind.access_invite",
  );
  expect(noticeKey({ kind: "share_invite", title_key: "notification.caregiver_invite" })).toBe(
    "kind.share_invite",
  );
});
