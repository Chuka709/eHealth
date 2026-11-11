import { fireEvent, renderRouter, screen, waitFor } from "expo-router/testing-library";
import { createMMKV } from "react-native-mmkv";

import { clearAccessToken, setStatus } from "@/features/auth/session-store";
import { setBiometricOn, setLocked } from "@/features/lock/lock-store";
import { apiBaseUrl } from "@/lib/api-base";
import { queryClient } from "@/lib/query-client";

const mockStore = new Map<string, string>();
const mockGate = { ok: false };
jest.mock("expo-secure-store", () => ({
  WHEN_UNLOCKED_THIS_DEVICE_ONLY: 6,
  WHEN_PASSCODE_SET_THIS_DEVICE_ONLY: 4,
  getItemAsync: jest.fn(async (key: string, options?: { requireAuthentication?: boolean }) => {
    if (options?.requireAuthentication && !mockGate.ok) throw new Error("user cancel");
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
  isEnrolledAsync: jest.fn(async () => true),
  SecurityLevel: { NONE: 0, SECRET: 1, BIOMETRIC_WEAK: 2, BIOMETRIC_STRONG: 3 },
  getEnrolledLevelAsync: jest.fn(async () => 3),
  authenticateAsync: jest.fn(async () => ({ success: false })),
}));

const mockFetch = jest.fn<Promise<Response>, [Request]>();
const json = (status: number, body: unknown) =>
  new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
const apiCalls = () => mockFetch.mock.calls.map(([r]) => r.url.slice(apiBaseUrl.length));

const ACCOUNT = "00000000-0000-4000-8000-000000000001";
const OWN_ID = "00000000-0000-4000-8000-0000000000aa";
const OWN = {
  id: OWN_ID,
  relation: "self",
  access_level: "owner",
  full_name: "Бат",
  birth_date: null,
  sex: "unknown",
  is_minor: false,
  consent_required: false,
  created_at: "2026-01-01T00:00:00Z",
};
const CARD = {
  patient: { full_name: "Бат", birth_date: null, sex: "unknown" },
  blood_type: "A+",
  blood_type_withheld: null,
  transplants: [],
  dosed_medications: [],
  other_medications: [],
  allergies: [{ substance: "Пенициллин", reaction: null, severity: "severe" }],
  contacts: [],
  generated_at: "2026-11-01T02:00:00Z",
};
const given = ["terms", "privacy", "sensitive_data", "ai_processing", "cross_border"].map(
  (kind) => ({
    kind,
    current_version: "draft-2026-10",
    granted: ["terms", "privacy", "sensitive_data"].includes(kind),
    granted_version: "draft-2026-10",
    at: "2026-10-01T00:00:00Z",
    required: ["terms", "privacy", "sensitive_data"].includes(kind),
  }),
);
const P = `/api/v1/patients/${OWN_ID}`;
const routes: Record<string, () => Response> = {
  "/api/v1/auth/refresh": () =>
    json(200, { access_token: "a1", token_type: "bearer", expires_in: 900, refresh_token: "r1" }),
  "/api/v1/me": () => json(200, { locale: "mn", display_name: "Бат Болд" }),
  "/api/v1/me/consents": () => json(200, given),
  "/api/v1/me/notifications": () => json(200, []),
  "/api/v1/patients": () => json(200, [OWN]),
  [`${P}/transplants`]: () => json(200, []),
  [`${P}/medications`]: () => json(200, []),
  [`${P}/appointments`]: () => json(200, []),
  [`${P}/intakes`]: () => json(200, []),
  [`${P}/timezone`]: () =>
    json(200, { home: "Asia/Ulaanbaatar", current: "Asia/Ulaanbaatar", switches: [] }),
  [`${P}/emergency-card`]: () => json(200, CARD),
};

// the phone's encrypted store as a previous session left it (keyring in the Keychain)
const STORE_ID = "lt.local.unlockedtest";
const device = () => createMMKV({ id: STORE_ID, encryptionKey: "k", encryptionType: "AES-256" });
const SNAPSHOT = `snapshot.emergency-card.v1.${OWN_ID}`;
const SETTING = "prefs.emergency_unlocked.v1";

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
  mockStore.set("lt.account", ACCOUNT);
  mockStore.set("lt.local_store", JSON.stringify({ id: STORE_ID, key: "k", account: ACCOUNT }));
  device().clearAll();
  device().set(SNAPSHOT, JSON.stringify(CARD));
  mockGate.ok = false; // the automatic prompt is cancelled: the app stays locked
  mockFetch.mockReset();
  mockFetch.mockImplementation(async (input: Request | string, init?: RequestInit) => {
    const request = typeof input === "string" ? new Request(input, init) : input;
    const path = request.url.slice(apiBaseUrl.length).split("?")[0];
    return routes[path]?.() ?? json(200, { status: "ok" });
  });
  globalThis.fetch = mockFetch as unknown as typeof fetch;
});

const coldStart = () => renderRouter("./src/app", { initialUrl: "/" });

test("off by default: the locked app offers no card, even with one saved (decision 10e)", async () => {
  await coldStart();
  expect(await screen.findByText("LabTrack MN түгжээтэй")).toBeOnTheScreen();
  await screen.findByRole("button", { name: "Түгжээ тайлах" });
  expect(
    screen.queryByRole("button", {
      name: "Яаралтай тусламжийн карт нээх. Open the emergency card",
    }),
  ).toBeNull();
  expect(apiCalls()).toEqual([]);
});

test("allowed: the locked app opens only the saved card, with no API call (H17, H22)", async () => {
  device().set(SETTING, JSON.stringify([OWN_ID]));
  await coldStart();
  await fireEvent.press(
    await screen.findByRole("button", {
      name: "Яаралтай тусламжийн карт нээх. Open the emergency card",
    }),
  );
  expect(await screen.findByText("Нэр: Бат")).toBeOnTheScreen();
  expect(screen.getByText("Пенициллин — Хүнд")).toBeOnTheScreen();
  expect(screen.getByText(/Утсанд хадгалсан хувилбар \(2026\.11\.01 10:00\)/)).toBeOnTheScreen();
  // nothing else of the account: no tabs, no other screen
  expect(screen.queryByTestId("home-screen")).toBeNull();
  expect(screen.queryByText("Эм")).toBeNull();
  expect(apiCalls()).toEqual([]);

  await fireEvent.press(screen.getByRole("button", { name: "Түгжээний дэлгэц рүү буцах" }));
  expect(await screen.findByText("LabTrack MN түгжээтэй")).toBeOnTheScreen();
  expect(apiCalls()).toEqual([]);
});

test("allowed: the biometric prompt is not raised by itself over the 🆘 button", async () => {
  device().set(SETTING, JSON.stringify([OWN_ID]));
  mockGate.ok = true; // a prompt would unlock at once
  const SecureStore = jest.requireMock<{ getItemAsync: jest.Mock }>("expo-secure-store");
  SecureStore.getItemAsync.mockClear(); // calls of earlier tests
  await coldStart();
  await screen.findByRole("button", { name: /Open the emergency card/ });
  const prompted = SecureStore.getItemAsync.mock.calls.some(
    ([, options]) =>
      (options as { requireAuthentication?: boolean } | undefined)?.requireAuthentication,
  );
  expect(prompted).toBe(false);
  expect(screen.getByText("LabTrack MN түгжээтэй")).toBeOnTheScreen();
  // the owner unlocks with one press
  await fireEvent.press(screen.getByRole("button", { name: "Түгжээ тайлах" }));
  expect(await screen.findByTestId("home-screen")).toBeOnTheScreen();
});

test.each(["{", '"x"', "[1,null]", '["not-an-id"]'])(
  "a damaged or tampered setting (%s) enables nothing",
  async (raw) => {
    device().set(SETTING, raw);
    await coldStart();
    await screen.findByRole("button", { name: "Түгжээ тайлах" });
    expect(screen.queryByRole("button", { name: /Open the emergency card/ })).toBeNull();
  },
);

test("allowed but nothing saved (e.g. a consent withdrawn): no card is offered", async () => {
  device().set(SETTING, JSON.stringify([OWN_ID]));
  device().remove(SNAPSHOT);
  await coldStart();
  await screen.findByRole("button", { name: "Түгжээ тайлах" });
  expect(
    screen.queryByRole("button", {
      name: "Яаралтай тусламжийн карт нээх. Open the emergency card",
    }),
  ).toBeNull();
});

test("Settings: off by default, the risk is said, and turning it on stays on this phone", async () => {
  mockGate.ok = true; // the automatic prompt unlocks
  await coldStart();
  await fireEvent.press(await screen.findByRole("button", { name: /^Тохиргоо, tab/ }));
  await fireEvent.press(await screen.findByTestId("settings-emergency"));
  expect(await screen.findByText(/хэн ч .* энэ картыг/)).toBeOnTheScreen();
  expect(device().getString(SETTING)).toBeUndefined(); // off until the user turns it on
  const before = apiCalls().length;
  await fireEvent(screen.getByTestId("emergency-unlocked"), "valueChange", true);
  await waitFor(() => expect(device().getString(SETTING)).toBe(JSON.stringify([OWN_ID])));
  // a device choice: nothing about it is sent to the server
  expect(
    apiCalls()
      .slice(before)
      .filter((p) => !p.startsWith(`${P}/`)),
  ).toEqual([]);
  await fireEvent(screen.getByTestId("emergency-unlocked"), "valueChange", false);
  await waitFor(() => expect(device().getString(SETTING)).toBe("[]"));
});

test("the one-time offer on Home: 'Not now' keeps it off and does not ask again", async () => {
  mockGate.ok = true;
  await coldStart();
  expect(await screen.findByTestId("emergency-offer")).toBeOnTheScreen();
  expect(screen.getByText(/хэн ч .* энэ картыг/)).toBeOnTheScreen();
  await fireEvent.press(screen.getByRole("button", { name: "Одоо биш" }));
  await waitFor(() => expect(screen.queryByTestId("emergency-offer")).toBeNull());
  expect(device().getString(SETTING)).toBe("[]"); // stored as off: the last answer wins
  expect(device().getBoolean("prefs.emergency_offered.v1")).toBe(true);
});

test("the one-time offer on Home: 'Turn on' allows the card for the own profile", async () => {
  mockGate.ok = true;
  device().remove(SNAPSHOT); // never opened: the app saves the card by itself
  await coldStart();
  await fireEvent.press(await screen.findByRole("button", { name: "Асаах" }));
  await waitFor(() => expect(device().getString(SETTING)).toBe(JSON.stringify([OWN_ID])));
  await waitFor(() => expect(screen.queryByTestId("emergency-offer")).toBeNull());
  // the locked app will have a card to show without the user ever opening it (H17)
  await waitFor(() => expect(device().getString(SNAPSHOT)).toBe(JSON.stringify(CARD)));
});
