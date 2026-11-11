import { renderHook } from "@testing-library/react-native";
import { fireEvent, renderRouter, screen, waitFor } from "expo-router/testing-library";

import { clearAccessToken, setStatus } from "@/features/auth/session-store";
import { apiBaseUrl } from "@/lib/api-base";
import { queryClient } from "@/lib/query-client";

import { chooseProfile, isOthers, resetActiveProfile, usePinnedProfile } from "./active-profile";
import type { Patient } from "./use-profile";

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

const allergy = (id: string, substance: string) => ({
  id,
  substance,
  reaction: null,
  severity: "severe",
  noted_on: null,
  created_at: "",
  updated_at: null,
});

const handlers: Record<string, Handler> = {
  "POST /api/v1/auth/refresh": () =>
    json(200, { access_token: "a1", token_type: "bearer", expires_in: 900, refresh_token: "r1" }),
  "GET /api/v1/me": () => json(200, { locale: "mn", display_name: "Бат Болд" }),
  "GET /api/v1/me/consents": () => json(200, allGiven),
  "GET /api/v1/me/notifications": () => json(200, []),
  "GET /api/v1/healthz": () => json(200, { status: "ok" }),
  "GET /api/v1/patients": () => json(200, [OWN, MOTHER]),
};
for (const p of [OWN, MOTHER]) {
  const base = `/api/v1/patients/${p.id}`;
  handlers[`GET ${base}/transplants`] = () => json(200, []);
  handlers[`GET ${base}/medications`] = () => json(200, []);
  handlers[`GET ${base}/timezone`] = () =>
    json(200, { home: "Asia/Ulaanbaatar", current: "Asia/Ulaanbaatar", switches: [] });
  for (const kind of ["events", "contacts", "appointments", "questions", "vitals"]) {
    handlers[`GET ${base}/${kind}`] = () => json(200, []);
  }
  handlers[`GET ${base}/allergies`] = () =>
    json(200, [allergy(`a-${p.id}`, p === OWN ? "Пенициллин" : "Сульфаниламид")]);
}

beforeEach(() => {
  queryClient.clear();
  clearAccessToken();
  setStatus("loading");
  resetActiveProfile();
  mockStore.clear();
  mockStore.set("lt.refresh", "r0");
  mockStore.set("lt.account", "00000000-0000-4000-8000-000000000001");
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

test("the record screens follow the chosen profile and say whose it is", async () => {
  await renderRouter("./src/app", { initialUrl: "/" });
  await fireEvent.press(await screen.findByRole("button", { name: /^Профайл,/ }));
  expect(await screen.findByText("Пенициллин")).toBeOnTheScreen();
  await fireEvent.press(await screen.findByTestId("profile-switcher"));
  await fireEvent.press(await screen.findByRole("radio", { name: /Дулмаа · асран хамгаалагч/ }));
  expect(await screen.findByText("Сульфаниламид")).toBeOnTheScreen();
  expect(screen.queryByText("Пенициллин")).toBeNull();
  expect(screen.getByText("👤 Профайл: Дулмаа")).toBeOnTheScreen();
  expect(screen.getByText(/Та түүний өмнөөс харж, тэмдэглэж байна/)).toBeOnTheScreen();
  // every record screen of hers says so too (H20)
  await fireEvent.press(screen.getByText("Сульфаниламид"));
  expect(await screen.findByText(/Одоо харж буй профайл: Дулмаа/)).toBeOnTheScreen();
});

test("a profile no longer shared falls back to the user's own", () => {
  const [own, mother] = [OWN, MOTHER] as unknown as Patient[];
  expect(chooseProfile([own, mother], mother.id)?.id).toBe(mother.id);
  expect(chooseProfile([own], mother.id)?.id).toBe(own.id);
  expect(chooseProfile([own, mother], null)?.id).toBe(own.id);
  expect(chooseProfile(undefined, mother.id)).toBeUndefined();
});

test("the emergency card and its saved copy stay the user's own on someone else's profile", async () => {
  await renderRouter("./src/app", { initialUrl: "/" });
  await fireEvent.press(await screen.findByRole("button", { name: /^Профайл,/ }));
  await fireEvent.press(await screen.findByTestId("profile-switcher"));
  await fireEvent.press(await screen.findByRole("radio", { name: /Дулмаа · асран хамгаалагч/ }));
  expect(await screen.findByText("Сульфаниламид")).toBeOnTheScreen();
  await fireEvent.press(await screen.findByRole("button", { name: /^Нүүр,/ }));
  await fireEvent.press(await screen.findByTestId("emergency-open"));
  const urls = () => mockFetch.mock.calls.map(([r]) => String((r as Request).url ?? r));
  await waitFor(() =>
    expect(urls().some((u) => u.includes(`${OWN.id}/emergency-card`))).toBe(true),
  );
  expect(urls().some((u) => u.includes(`${MOTHER.id}/emergency-card`))).toBe(false);
});

test("a form keeps the profile it was opened on; a change blocks saving", async () => {
  const [own, mother] = [OWN, MOTHER] as unknown as Patient[];
  const { result, rerender } = await renderHook(
    ({ p }: { p: Patient | undefined }) => usePinnedProfile(p),
    {
      initialProps: { p: undefined as Patient | undefined },
    },
  );
  expect(result.current).toEqual({ pinned: undefined, changed: false }); // still loading
  await rerender({ p: mother });
  expect(result.current).toEqual({ pinned: mother, changed: false });
  await rerender({ p: own }); // access ended: the own profile took over
  expect(result.current).toEqual({ pinned: undefined, changed: true });
  // a child's profile is someone else's too (the screens say whose it is)
  const child = { ...own, id: "child-1", relation: "child" } as Patient;
  expect(isOthers(child, [own, child])).toBe(true);
  expect(isOthers(own, [own, child])).toBe(false);
});
