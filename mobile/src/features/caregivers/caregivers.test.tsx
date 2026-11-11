import { fireEvent, renderRouter, screen, waitFor } from "expo-router/testing-library";
import { Alert } from "react-native";

import { clearAccessToken, setStatus } from "@/features/auth/session-store";
import { setCardUnlocked, unlockedProfiles } from "@/features/emergency/unlocked";
import { resetActiveProfile, setActiveProfile } from "@/features/records/active-profile";
import { dropMissingProfiles } from "@/features/records/use-profile";
import { apiBaseUrl } from "@/lib/api-base";
import { localStore } from "@/lib/local-store";
import { SNAPSHOT_PREFIX } from "@/lib/persist";
import { queryClient } from "@/lib/query-client";

import { alertingCaregivers } from "./use-caregivers";

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

const allGivenWithSharing = [
  ...allGiven,
  {
    kind: "caregiver_sharing",
    current_version: "draft-2026-11",
    granted: true,
    granted_version: "draft-2026-11",
    at: "2026-11-01T00:00:00Z",
    required: false,
  },
];
let inviteStatus = 202;
let posts: { path: string; body: unknown }[] = [];
let alerts: Record<string, unknown> = {};
const record = (path: string) => async (request: Request) => {
  posts.push({ path, body: await request.json().catch(() => null) });
  return new Response(null, { status: 204 });
};

const handlers: Record<string, Handler> = {
  "POST /api/v1/auth/refresh": () =>
    json(200, { access_token: "a1", token_type: "bearer", expires_in: 900, refresh_token: "r1" }),
  "GET /api/v1/me": () => json(200, { locale: "mn", display_name: "Бат Болд" }),
  "GET /api/v1/me/consents": () => json(200, allGivenWithSharing),
  "POST /api/v1/me/consents": record("consents"),
  "GET /api/v1/me/notifications": () => json(200, []),
  "GET /api/v1/healthz": () => json(200, { status: "ok" }),
  "GET /api/v1/patients": () => json(200, [OWN, MOTHER]),
  "GET /api/v1/me/caregiver-invitations": () =>
    json(200, [
      {
        id: "inv-1",
        inviter_name: "Дулмаа",
        created_at: "2026-11-10T00:00:00Z",
        expires_at: "2026-11-24T00:00:00Z",
      },
    ]),
  "POST /api/v1/me/caregiver-invitations/respond": record("respond"),
  [`POST /api/v1/patients/${MOTHER.id}/leave`]: record("leave"),
  [`GET /api/v1/patients/${OWN.id}/caregivers`]: () =>
    json(200, {
      caregivers: [
        {
          user_id: "u-2",
          display_name: "Сараа",
          since: "2026-11-01T00:00:00Z",
          missed_dose_after_min: 30,
          critical_result: false,
          owner_paused: false,
        },
      ],
      invitations: [],
    }),
  [`POST /api/v1/patients/${OWN.id}/caregiver-invitations`]: async (request) => {
    posts.push({ path: "invite", body: await request.json() });
    return inviteStatus === 202
      ? new Response(null, { status: 202 })
      : json(inviteStatus, {
          code: "caregiver.consent_required",
          message_key: "error.caregiver.consent_required",
        });
  },
  [`GET /api/v1/patients/${MOTHER.id}/caregiver-alerts`]: () => json(200, alerts),
  [`PUT /api/v1/patients/${MOTHER.id}/caregiver-alerts`]: async (request) => {
    const body = (await request.json()) as Record<string, unknown>;
    posts.push({ path: "alerts", body });
    alerts = { ...alerts, ...body, chosen: true };
    return json(200, alerts);
  },
};
for (const p of [OWN, MOTHER]) {
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
  inviteStatus = 202;
  posts = [];
  asked = [];
  alerts = {
    missed_dose_after_min: null,
    critical_result: false,
    owner_paused: false,
    chosen: false,
    watched_medications: 2,
  };
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

test("the owner invites by username after checking it, and sees the caregivers", async () => {
  await openTab(/^Профайл,/);
  await fireEvent.press(await screen.findByTestId("profile-caregivers"));
  expect(await screen.findByText("Сараа")).toBeOnTheScreen();
  expect(
    screen.getByText("Мэдэгдэл: эм уусан тэмдэглэл 30 минут бүртгэгдээгүй бол"),
  ).toBeOnTheScreen();
  await fireEvent.changeText(screen.getByTestId("caregiver-username"), " Sara.B ");
  await fireEvent.press(screen.getByRole("button", { name: "Урих" }));
  expect(asked[0]).toMatch(/«sara.b» — зөв үү/);
  await waitFor(() =>
    expect(posts).toContainEqual({ path: "invite", body: { username: "sara.b" } }),
  );
  expect(await screen.findByText(/Илгээгдлээ/)).toBeOnTheScreen();
});

test("without the sharing consent the owner is sent to give it", async () => {
  inviteStatus = 409;
  await openTab(/^Профайл,/);
  await fireEvent.press(await screen.findByTestId("profile-caregivers"));
  await fireEvent.changeText(await screen.findByTestId("caregiver-username"), "sara.b");
  await fireEvent.press(screen.getByRole("button", { name: "Урих" }));
  expect(await screen.findByText("Зөвшөөрөл рүү очих")).toBeOnTheScreen();
  expect(screen.getByText(/«Асран хамгаалагчтай хуваалцах» зөвшөөрлөө өгнө үү/)).toBeOnTheScreen();
});

test("an invitation is answered: yes after saying what it means, or no", async () => {
  await openTab(/^Тохиргоо,/);
  await fireEvent.press(await screen.findByTestId("settings-invitations"));
  expect(await screen.findByText("Дулмаа таныг асран хамгаалагчаар урьж байна")).toBeOnTheScreen();
  await fireEvent.press(screen.getByRole("button", { name: "Урилгаас татгалзах — Дулмаа" }));
  await waitFor(() =>
    expect(posts).toContainEqual({
      path: "respond",
      body: { invitation_id: "inv-1", accept: false },
    }),
  );
  await fireEvent.press(await screen.findByRole("button", { name: "Урилгыг зөвшөөрөх — Дулмаа" }));
  expect(asked.some((a) => a.includes("бичлэг нэмж чадна"))).toBe(true);
  await waitFor(() =>
    expect(posts).toContainEqual({
      path: "respond",
      body: { invitation_id: "inv-1", accept: true },
    }),
  );
});

test("a caregiver's alerts: 30 minutes offered, what is watched, what no alert means", async () => {
  setActiveProfile(MOTHER.id);
  await openTab(/^Профайл,/);
  await fireEvent.press(await screen.findByTestId("profile-caregiver-alerts"));
  expect(await screen.findByRole("radio", { name: "30 минут", selected: true })).toBeOnTheScreen();
  expect(screen.getByText("Хянагдаж буй эм: 2")).toBeOnTheScreen();
  expect(screen.getByText(/Мэдэгдэл ирээгүй нь эм уусан гэсэн үг биш/)).toBeOnTheScreen();
  await fireEvent.press(screen.getByRole("radio", { name: "15 минут" }));
  expect(screen.getByText(/10 хүртэл минут хоцорч болох/)).toBeOnTheScreen();
  await fireEvent.press(screen.getByRole("button", { name: "Хадгалах" }));
  await waitFor(() =>
    expect(posts).toContainEqual({
      path: "alerts",
      body: { missed_dose_after_min: 15, critical_result: false },
    }),
  );
});

test("withdrawing the sharing consent says first that every caregiver loses access", async () => {
  await openTab(/^Тохиргоо,/);
  await fireEvent.press(await screen.findByTestId("settings-consents"));
  await fireEvent(await screen.findByTestId("consent-settings-caregiver"), "valueChange", false);
  expect(asked[0]).toMatch(/Бүх асран хамгаалагч таны профайлыг харах/);
  await waitFor(() =>
    expect(posts).toContainEqual({
      path: "consents",
      body: { items: [{ kind: "caregiver_sharing", granted: false, version: "draft-2026-11" }] },
    }),
  );
});

test("only caregivers who get alerts count for the reminders-off note", () => {
  const c = (min: number | null, paused: boolean) => ({
    user_id: "u",
    display_name: "x",
    since: null,
    missed_dose_after_min: min,
    critical_result: false,
    owner_paused: paused,
  });
  expect(
    alertingCaregivers({
      caregivers: [c(30, false), c(null, false), c(30, true)],
      invitations: [],
    }),
  ).toBe(1);
  expect(alertingCaregivers(undefined)).toBe(0);
});

test("leaving as caregiver drops what the phone kept of that person", async () => {
  setActiveProfile(MOTHER.id);
  await openTab(/^Профайл,/);
  queryClient.setQueryData(["medications", MOTHER.id], [{ id: "m1", regimens: [] }]);
  queryClient.setQueryData(["medications", OWN.id], [{ id: "m0", regimens: [] }]);
  await fireEvent.press(await screen.findByTestId("profile-caregiver-alerts"));
  await fireEvent.press(
    await screen.findByRole("button", { name: /Асран хамгаалагчаас гарах: Дулмаа/ }),
  );
  await waitFor(() => expect(posts.some((p) => p.path === "leave")).toBe(true));
  await waitFor(() => expect(queryClient.getQueryData(["medications", MOTHER.id])).toBeUndefined());
  expect(queryClient.getQueryData(["medications", OWN.id])).toEqual([{ id: "m0", regimens: [] }]);
});

test("a profile gone from the list leaves the cache too (access ended, Q42)", () => {
  queryClient.setQueryData(["records", MOTHER.id, "allergies"], [{ id: "a" }]);
  queryClient.setQueryData(["records", OWN.id, "allergies"], [{ id: "b" }]);
  queryClient.setQueryData(["me", "notifications"], []);
  void dropMissingProfiles([OWN]);
  expect(queryClient.getQueryData(["records", MOTHER.id, "allergies"])).toBeUndefined();
  expect(queryClient.getQueryData(["records", OWN.id, "allergies"])).toEqual([{ id: "b" }]);
  expect(queryClient.getQueryData(["me", "notifications"])).toEqual([]);
});

test("a profile gone from the list leaves no saved emergency card or lock-screen opening", async () => {
  setStatus("signedIn"); // the encrypted store opens for a signed-in account only
  const store = await localStore();
  const card = (id: string) => `${SNAPSHOT_PREFIX}emergency-card.v1.${id}`;
  store.set(card(OWN.id), "{}");
  store.set(card(MOTHER.id), "{}");
  await setCardUnlocked(OWN.id, true);
  await setCardUnlocked(MOTHER.id, true);
  await dropMissingProfiles([OWN]);
  expect(await unlockedProfiles()).toEqual([OWN.id]);
  expect(store.getString(card(MOTHER.id))).toBeUndefined();
  expect(store.getString(card(OWN.id))).toBe("{}");
});
