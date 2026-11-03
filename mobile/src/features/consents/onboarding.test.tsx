import { fireEvent, renderRouter, screen } from "expo-router/testing-library";
import { Alert } from "react-native";

import { clearAccessToken, setStatus } from "@/features/auth/session-store";
import { apiBaseUrl } from "@/lib/api-base";
import { queryClient } from "@/lib/query-client";

const mockStore = new Map<string, string>();
const mockBio = { hardware: true, enrolled: true, success: true };

jest.mock("expo-secure-store", () => ({
  WHEN_UNLOCKED_THIS_DEVICE_ONLY: 6,
  WHEN_PASSCODE_SET_THIS_DEVICE_ONLY: 4,
  // Items with requireAuthentication stand behind the biometric prompt (mockBio.success).
  getItemAsync: jest.fn(async (key: string, options?: { requireAuthentication?: boolean }) => {
    if (options?.requireAuthentication && !mockBio.success) throw new Error("user cancel");
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
  hasHardwareAsync: jest.fn(async () => mockBio.hardware),
  isEnrolledAsync: jest.fn(async () => mockBio.enrolled),
  SecurityLevel: { NONE: 0, SECRET: 1, BIOMETRIC_WEAK: 2, BIOMETRIC_STRONG: 3 },
  getEnrolledLevelAsync: jest.fn(async () => (mockBio.enrolled ? 3 : 1)),
  authenticateAsync: jest.fn(async () =>
    mockBio.success ? { success: true } : { success: false, error: "user_cancel" },
  ),
}));

type Handler = (request: Request) => Promise<Response> | Response;
const mockFetch = jest.fn<Promise<Response>, [Request]>();
const json = (status: number, body: unknown) =>
  new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
const tokens = () =>
  json(200, { access_token: "a1", token_type: "bearer", expires_in: 900, refresh_token: "r1" });

type Kind = "terms" | "privacy" | "sensitive_data" | "ai_processing" | "cross_border";
const KINDS: Kind[] = ["terms", "privacy", "sensitive_data", "ai_processing", "cross_border"];
const isRequired = (kind: Kind) => ["terms", "privacy", "sensitive_data"].includes(kind);
/** Consent states as the server reports them; `given` maps kind → version last given. */
const states = (given: Partial<Record<Kind, string>> = {}, current = "draft-2026-10") =>
  KINDS.map((kind) => ({
    kind,
    current_version: current,
    granted: given[kind] === current,
    granted_version: given[kind] ?? null,
    at: given[kind] ? "2026-10-01T00:00:00Z" : null,
    required: isRequired(kind),
  }));

let consentState = states();
const posted: unknown[] = [];

function route(extra: Record<string, Handler> = {}) {
  const handlers: Record<string, Handler> = {
    "/api/v1/auth/refresh": tokens,
    "/api/v1/healthz": () => json(200, { status: "ok" }),
    "/api/v1/me/consents": async (request) => {
      if (request.method === "GET") return json(200, consentState);
      const body = (await request.json()) as {
        items: { kind: Kind; version: string; granted: boolean }[];
      };
      posted.push(body);
      const given = Object.fromEntries(
        body.items.filter((i) => i.granted).map((i) => [i.kind, i.version]),
      );
      consentState = states(given);
      return new Response(null, { status: 204 });
    },
    ...extra,
  };
  mockFetch.mockImplementation(async (input: Request | string, init?: RequestInit) => {
    const request = typeof input === "string" ? new Request(input, init) : input;
    const handler = handlers[request.url.slice(apiBaseUrl.length)];
    if (!handler) throw new Error(`unexpected ${request.url}`);
    return handler(request);
  });
}

beforeEach(() => {
  // Module state shared by the app (cache, session) must not leak between tests.
  queryClient.clear();
  clearAccessToken();
  setStatus("loading");
  mockStore.clear();
  mockStore.set("lt.refresh", "r0"); // signed in
  Object.assign(mockBio, { hardware: true, enrolled: true, success: true });
  consentState = states();
  posted.length = 0;
  mockFetch.mockReset();
  globalThis.fetch = mockFetch as unknown as typeof fetch;
  route();
});

const app = () => renderRouter("./src/app", { initialUrl: "/" });
const toggle = async (kind: string) =>
  fireEvent(await screen.findByTestId(`consent-${kind}`), "valueChange", true);

test("a new user must give the three required consents before anything else", async () => {
  await app();
  expect(await screen.findByText("Зөвшөөрөл")).toBeOnTheScreen();
  expect(screen.getByText(/хуульчийн хяналт/)).toBeOnTheScreen(); // draft texts are marked
  // Continue without them: explained, nothing sent.
  await fireEvent.press(screen.getByRole("button", { name: "Үргэлжлүүлэх" }));
  expect(await screen.findByText(/заавал гэсэн гурван зөвшөөрлийг/)).toBeOnTheScreen();
  expect(posted).toHaveLength(0);

  for (const kind of ["terms", "privacy", "sensitive_data"]) await toggle(kind);
  await fireEvent.press(screen.getByRole("button", { name: "Үргэлжлүүлэх" }));

  // Next: the one-time biometric offer.
  expect(await screen.findByText("Аппыг хурдан, аюулгүй нээх")).toBeOnTheScreen();
  // Only the required ones, for the version shown; the AI pair stays off and is not sent.
  expect(posted).toEqual([
    {
      items: [
        { kind: "terms", granted: true, version: "draft-2026-10" },
        { kind: "privacy", granted: true, version: "draft-2026-10" },
        { kind: "sensitive_data", granted: true, version: "draft-2026-10" },
      ],
    },
  ]);
});

test("the AI consent sends both processing and transfer abroad", async () => {
  await app();
  for (const kind of ["terms", "privacy", "sensitive_data", "ai"]) await toggle(kind);
  await fireEvent.press(await screen.findByRole("button", { name: "Үргэлжлүүлэх" }));
  await screen.findByText("Аппыг хурдан, аюулгүй нээх");
  const items = (posted[0] as { items: { kind: string; granted: boolean }[] }).items;
  expect(items.filter((i) => i.kind === "ai_processing" || i.kind === "cross_border")).toEqual([
    { kind: "ai_processing", granted: true, version: "draft-2026-10" },
    { kind: "cross_border", granted: true, version: "draft-2026-10" },
  ]);
});

test("a changed text version asks again and says why", async () => {
  consentState = states(
    { terms: "draft-2026-09", privacy: "draft-2026-09", sensitive_data: "draft-2026-09" },
    "draft-2026-10",
  );
  await app();
  expect(await screen.findByText(/Нөхцөл шинэчлэгдсэн/)).toBeOnTheScreen();
});

test("declining explains why the app cannot be used and offers sign-out", async () => {
  await app();
  await fireEvent.press(await screen.findByRole("button", { name: "Зөвшөөрөхгүй" }));
  expect(await screen.findByText(/аппыг ашиглах боломжгүй/)).toBeOnTheScreen();
  expect(screen.getByRole("button", { name: "Гарах" })).toBeOnTheScreen();
  await fireEvent.press(screen.getByRole("button", { name: "Зөвшөөрөл рүү буцах" }));
  expect(await screen.findByText("Зөвшөөрөл")).toBeOnTheScreen();
});

test("a newer text on the server than in this app: update first, never consent", async () => {
  consentState = states({}, "draft-2026-11");
  await app();
  expect(await screen.findByText(/аппаа шинэчилнэ үү/)).toBeOnTheScreen();
  expect(screen.queryByTestId("consent-terms")).toBeNull();
  expect(posted).toHaveLength(0);
});

test("a version changed while answering: nothing is assumed, the app asks for an update", async () => {
  route({
    "/api/v1/me/consents": async (request) => {
      if (request.method === "GET") return json(200, consentState);
      consentState = states({}, "draft-2026-11"); // the server moved on meanwhile
      return json(409, { code: "consent.version_outdated", message_key: "x" });
    },
  });
  await app();
  for (const kind of ["terms", "privacy", "sensitive_data"]) await toggle(kind);
  await fireEvent.press(screen.getByRole("button", { name: "Үргэлжлүүлэх" }));
  expect(await screen.findByText(/аппаа шинэчилнэ үү/)).toBeOnTheScreen();
});

test("pressing continue too early marks each missing required consent", async () => {
  await app();
  await toggle("terms");
  await fireEvent.press(screen.getByRole("button", { name: "Үргэлжлүүлэх" }));
  expect(await screen.findAllByText("Заавал — өгөөгүй байна.")).toHaveLength(2);
});

describe("biometric offer", () => {
  beforeEach(() => {
    consentState = states({
      terms: "draft-2026-10",
      privacy: "draft-2026-10",
      sensitive_data: "draft-2026-10",
    });
  });

  test("enable creates the biometric-bound unlock key, proves it opens, then opens the app", async () => {
    const SecureStore = jest.requireMock<{ setItemAsync: jest.Mock }>("expo-secure-store");
    await app();
    await fireEvent.press(await screen.findByRole("button", { name: "Биометрээр түгжих" }));
    expect(await screen.findByText("Системийн төлөв")).toBeOnTheScreen();
    expect(mockStore.get("lt.biometric")).toBe("on");
    expect(mockStore.get("lt.unlock_gate")).toBe("1");
    expect(SecureStore.setItemAsync).toHaveBeenCalledWith(
      "lt.unlock_gate",
      "1",
      expect.objectContaining({ requireAuthentication: true, keychainAccessible: 4 }),
    );
  });

  test("a failed confirmation stores nothing and says so", async () => {
    mockBio.success = false;
    await app();
    await fireEvent.press(await screen.findByRole("button", { name: "Биометрээр түгжих" }));
    expect(await screen.findByText(/Баталгаажуулж чадсангүй/)).toBeOnTheScreen();
    expect(mockStore.has("lt.biometric")).toBe(false);
    expect(mockStore.has("lt.unlock_gate")).toBe(false);
  });

  test("not now is remembered", async () => {
    await app();
    await fireEvent.press(await screen.findByRole("button", { name: "Одоо биш" }));
    expect(await screen.findByText("Системийн төлөв")).toBeOnTheScreen();
    expect(mockStore.get("lt.biometric")).toBe("off");
  });

  test("phones without enrolled biometrics are not asked", async () => {
    mockBio.enrolled = false;
    await app();
    expect(await screen.findByText("Системийн төлөв")).toBeOnTheScreen();
  });

  test("signing out forgets the choice (it belongs to the user, not the phone)", async () => {
    mockStore.set("lt.biometric", "off"); // "on" would open on the lock screen (lock.test.tsx)
    route({
      "/api/v1/auth/logout": () => new Response(null, { status: 204 }),
      "/api/v1/me": () => json(200, { locale: "mn" }),
    });
    // Sign-out lives in Settings and asks first: confirm the dialog.
    const alert = jest.spyOn(Alert, "alert").mockImplementation((_t, _m, buttons) => {
      buttons?.find((b) => b.style === "destructive")?.onPress?.();
    });
    await app();
    await fireEvent.press(await screen.findByRole("button", { name: "Тохиргоо" }));
    await fireEvent.press(await screen.findByRole("button", { name: "Гарах" }));
    expect(await screen.findByText("LabTrack MN-д тавтай морил")).toBeOnTheScreen();
    expect(mockStore.has("lt.biometric")).toBe(false);
    alert.mockRestore();
  });
});
