import { fireEvent, renderRouter, screen, waitFor } from "expo-router/testing-library";
import { Alert, type AlertButton } from "react-native";

import { clearAccessToken, getStatus, setStatus } from "@/features/auth/session-store";
import { setBiometricOn, setLocked } from "@/features/lock/lock-store";
import { apiBaseUrl } from "@/lib/api-base";
import { setLocale } from "@/lib/i18n";
import { queryClient } from "@/lib/query-client";

const mockStore = new Map<string, string>();
const mockGate = { ok: true, invalidated: false };

jest.mock("expo-secure-store", () => ({
  WHEN_UNLOCKED_THIS_DEVICE_ONLY: 6,
  WHEN_PASSCODE_SET_THIS_DEVICE_ONLY: 4,
  getItemAsync: jest.fn(async (key: string, options?: { requireAuthentication?: boolean }) => {
    if (options?.requireAuthentication && mockGate.invalidated) return null;
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
  SecurityLevel: { BIOMETRIC_STRONG: 3 },
  getEnrolledLevelAsync: jest.fn(async () => 3),
}));

type Handler = (request: Request) => Promise<Response> | Response;
const mockFetch = jest.fn<Promise<Response>, [Request]>();
const json = (status: number, body: unknown) =>
  new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
const err = (status: number, code: string) => json(status, { code, message_key: `error.${code}` });
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
let me = {
  id: "00000000-0000-0000-0000-000000000001",
  username: "bat.01",
  display_name: "Бат",
  locale: "mn",
  role: "user",
  account_status: "active",
  password_changed_at: null,
  created_at: "2026-10-01T00:00:00Z",
};
const sessions = [
  {
    id: "s-other",
    device_name: "Galaxy A54",
    platform: "android",
    created_at: "2026-10-20T02:00:00Z",
    last_used_at: "2026-11-01T03:00:00Z",
    current: false,
  },
  {
    id: "s-this",
    device_name: "Pixel 8",
    platform: "android",
    created_at: "2026-10-01T02:00:00Z",
    last_used_at: "2026-11-03T03:00:00Z",
    current: true,
  },
];

function route(extra: Record<string, Handler> = {}) {
  const handlers: Record<string, Handler> = {
    "GET /api/v1/auth/refresh": () => json(405, {}),
    "POST /api/v1/auth/refresh": () =>
      json(200, { access_token: "a1", token_type: "bearer", expires_in: 900, refresh_token: "r1" }),
    "GET /api/v1/me/consents": () => json(200, given),
    "GET /api/v1/me": () => json(200, me),
    "PATCH /api/v1/me": async (request) => {
      me = { ...me, ...((await request.json()) as object) };
      return json(200, me);
    },
    "GET /api/v1/auth/sessions": () => json(200, sessions),
    "DELETE /api/v1/auth/sessions/s-other": () => new Response(null, { status: 204 }),
    "POST /api/v1/auth/password": () => new Response(null, { status: 204 }),
    "POST /api/v1/auth/logout": () => new Response(null, { status: 204 }),
    "GET /api/v1/healthz": () => json(200, { status: "ok" }),
    "GET /api/v1/me/notifications": () => json(200, []),
    ...extra,
  };
  mockFetch.mockImplementation(async (input: Request | string, init?: RequestInit) => {
    const request = typeof input === "string" ? new Request(input, init) : input;
    const key = `${request.method} ${request.url.slice(apiBaseUrl.length).split("?")[0]}`;
    if (request.method !== "GET") sent.push([key, await request.clone().text()]);
    const handler = handlers[key];
    if (!handler) throw new Error(`unexpected ${key}`);
    return handler(request);
  });
}
/** JSON bodies sent to `key`, in order (read before the handler consumes them). */
const sent: [string, string][] = [];
const bodies = (key: string) =>
  sent.filter(([k]) => k === key).map(([, text]) => (text ? JSON.parse(text) : null));
const calls = (key: string) =>
  mockFetch.mock.calls.filter(([r]) => `${r.method} ${r.url.slice(apiBaseUrl.length)}` === key);

/** Presses the button of the most recent Alert whose text matches. */
const alert = jest.spyOn(Alert, "alert");
const confirm = (text: string) => {
  const buttons = alert.mock.calls.at(-1)?.[2] as AlertButton[] | undefined;
  buttons?.find((b) => b.text === text)?.onPress?.();
};

beforeEach(() => {
  queryClient.clear();
  clearAccessToken();
  setStatus("loading");
  setLocked(false);
  setBiometricOn(false);
  setLocale("mn");
  alert.mockClear();
  me = { ...me, display_name: "Бат", locale: "mn" };
  mockStore.clear();
  mockStore.set("lt.refresh", "r0");
  mockStore.set("lt.biometric", "off");
  mockStore.set("lt.device", "device-1");
  mockGate.ok = true;
  mockGate.invalidated = false;
  mockFetch.mockReset();
  sent.length = 0;
  globalThis.fetch = mockFetch as unknown as typeof fetch;
  route();
});

const openSettings = async () => {
  await renderRouter("./src/app", { initialUrl: "/" });
  await fireEvent.press(await screen.findByRole("button", { name: "Тохиргоо" }));
  await screen.findByTestId("settings-profile");
};

test("profile: rename and switch the whole app to English", async () => {
  await openSettings();
  await fireEvent.press(screen.getByTestId("settings-profile"));
  const name = await screen.findByLabelText("Харагдах нэр");
  await fireEvent.changeText(name, "Бат-Эрдэнэ");
  await fireEvent.press(screen.getByRole("button", { name: "Хадгалах" }));
  expect(await screen.findByText("Хадгалагдлаа.")).toBeOnTheScreen();
  expect(bodies("PATCH /api/v1/me")).toEqual([{ display_name: "Бат-Эрдэнэ" }]);

  await fireEvent.press(screen.getByRole("radio", { name: "English" }));
  expect(await screen.findByText("Display name")).toBeOnTheScreen();
});

describe("password change", () => {
  const fill = async (current: string, next: string, again = next) => {
    await fireEvent.changeText(await screen.findByLabelText("Одоогийн нууц үг"), current);
    await fireEvent.changeText(screen.getByLabelText("Шинэ нууц үг"), next);
    await fireEvent.changeText(screen.getByLabelText("Шинэ нууц үгээ давтах"), again);
    await fireEvent.press(screen.getByRole("button", { name: "Нууц үг солих" }));
  };
  const strong = "ногоон-цонх-гурван-морь";

  test("a wrong current password is shown on the field and keeps the session", async () => {
    route({ "POST /api/v1/auth/password": () => err(401, "auth.invalid_credentials") });
    await openSettings();
    await fireEvent.press(screen.getByTestId("settings-password"));
    await fill("wrong-one", strong);
    expect(await screen.findByText(/Одоогийн нууц үг буруу байна/)).toBeOnTheScreen();
    expect(calls("POST /api/v1/auth/password")).toHaveLength(1); // not replayed
    expect(getStatus()).toBe("signedIn");
  });

  test("signs out the other devices by default; the switch keeps them", async () => {
    await openSettings();
    await fireEvent.press(screen.getByTestId("settings-password"));
    await fill("old-password-1", strong);
    expect(await screen.findByText(/бусад төхөөрөмжөөс гарлаа/)).toBeOnTheScreen();
    expect(bodies("POST /api/v1/auth/password")[0]).toEqual({
      current_password: "old-password-1",
      new_password: strong,
      sign_out_other_devices: true,
      device_token: "device-1", // this phone keeps its trust, the others lose it
    });
    // The form is emptied: no password stays on screen.
    expect(screen.getByLabelText("Одоогийн нууц үг").props.value).toBe("");

    fireEvent(screen.getByTestId("password-sign-out-others"), "valueChange", false);
    await fill("old-password-2", strong);
    await screen.findByText("Нууц үг солигдлоо.");
    expect(bodies("POST /api/v1/auth/password")[1]?.sign_out_other_devices).toBe(false);
  });

  test("the new password must be long enough and repeated", async () => {
    await openSettings();
    await fireEvent.press(screen.getByTestId("settings-password"));
    await fill("old", "short", "other");
    expect(await screen.findByText(/дор хаяж 10 тэмдэгт/)).toBeOnTheScreen();
    expect(screen.getByText(/таарахгүй/)).toBeOnTheScreen();
    expect(calls("POST /api/v1/auth/password")).toHaveLength(0);
  });
});

describe("devices", () => {
  test("lists this device first and signs out another after confirming", async () => {
    await openSettings();
    await fireEvent.press(screen.getByTestId("settings-devices"));
    const names = await screen.findAllByRole("header");
    expect(
      names.map((n) => n.props.children).filter((c) => c !== "Нэвтэрсэн төхөөрөмжүүд"),
    ).toEqual(["Pixel 8", "Galaxy A54"]);
    expect(screen.getByText("● Энэ төхөөрөмж")).toBeOnTheScreen(); // badge: glyph + text

    await fireEvent.press(screen.getByRole("button", { name: "«Galaxy A54» төхөөрөмжийг гаргах" }));
    expect(calls("DELETE /api/v1/auth/sessions/s-other")).toHaveLength(0); // asks first
    confirm("Гаргах");
    expect(await screen.findByText("«Galaxy A54» төхөөрөмжийг гаргалаа.")).toBeOnTheScreen();
    expect(calls("DELETE /api/v1/auth/sessions/s-other")).toHaveLength(1);
  });

  test("signing out this device is a normal sign-out, never a DELETE of itself", async () => {
    await openSettings();
    await fireEvent.press(screen.getByTestId("settings-devices"));
    await fireEvent.press(await screen.findByRole("button", { name: "Энэ төхөөрөмжөөс гарах" }));
    confirm("Гарах");
    expect(await screen.findByText("LabTrack MN-д тавтай морил")).toBeOnTheScreen();
    expect(calls("DELETE /api/v1/auth/sessions/s-this")).toHaveLength(0);
    expect(mockStore.has("lt.refresh")).toBe(false);
  });
});

test("sign out asks first; cancelling keeps the session", async () => {
  await openSettings();
  await fireEvent.press(screen.getByRole("button", { name: "Гарах" }));
  confirm("Болих");
  expect(getStatus()).toBe("signedIn");
  await fireEvent.press(screen.getByRole("button", { name: "Гарах" }));
  confirm("Гарах");
  expect(await screen.findByText("LabTrack MN-д тавтай морил")).toBeOnTheScreen();
});

describe("biometric switch", () => {
  test("turning it on creates the unlock key", async () => {
    await openSettings();
    await fireEvent(screen.getByTestId("settings-biometric"), "valueChange", true);
    await waitFor(() => expect(mockStore.get("lt.biometric")).toBe("on"));
    expect(mockStore.get("lt.unlock_gate")).toBe("1");
  });

  test("turning it off needs the biometric; a failed check changes nothing", async () => {
    mockStore.set("lt.biometric", "on");
    mockStore.set("lt.unlock_gate", "1");
    await renderRouter("./src/app", { initialUrl: "/" });
    // Cold start is locked; the automatic prompt (succeeding here) unlocks it.
    await fireEvent.press(await screen.findByRole("button", { name: "Тохиргоо" }));
    await screen.findByTestId("settings-biometric");

    mockGate.ok = false;
    await fireEvent(screen.getByTestId("settings-biometric"), "valueChange", false);
    expect(await screen.findByText(/Тохиргоо өөрчлөгдсөнгүй/)).toBeOnTheScreen();
    expect(mockStore.get("lt.biometric")).toBe("on");
    expect(mockStore.get("lt.unlock_gate")).toBe("1");

    mockGate.ok = true;
    await fireEvent(screen.getByTestId("settings-biometric"), "valueChange", false);
    await waitFor(() => expect(mockStore.get("lt.biometric")).toBe("off"));
    expect(mockStore.has("lt.unlock_gate")).toBe(false);
  });
});

test("an invalidated unlock key cannot switch the lock off: the app locks instead", async () => {
  mockStore.set("lt.biometric", "on");
  mockStore.set("lt.unlock_gate", "1");
  await renderRouter("./src/app", { initialUrl: "/" });
  await fireEvent.press(await screen.findByRole("button", { name: "Тохиргоо" }));
  await screen.findByTestId("settings-biometric");

  mockGate.invalidated = true; // someone added a finger since the last unlock
  await fireEvent(screen.getByTestId("settings-biometric"), "valueChange", false);
  expect(await screen.findByText(/биометрийн тохиргоо өөрчлөгдсөн/)).toBeOnTheScreen();
  expect(mockStore.get("lt.biometric")).toBe("on");
});

test("pressing submit twice sends the password change once", async () => {
  let release: () => void = () => undefined;
  const gate = new Promise<void>((resolve) => {
    release = resolve;
  });
  route({
    "POST /api/v1/auth/password": async () => {
      await gate;
      return new Response(null, { status: 204 });
    },
  });
  await openSettings();
  await fireEvent.press(screen.getByTestId("settings-password"));
  const strong = "ногоон-цонх-гурван-морь";
  await fireEvent.changeText(await screen.findByLabelText("Одоогийн нууц үг"), "old-password-1");
  await fireEvent.changeText(screen.getByLabelText("Шинэ нууц үг"), strong);
  const confirmField = screen.getByLabelText("Шинэ нууц үгээ давтах");
  await fireEvent.changeText(confirmField, strong);
  await fireEvent(confirmField, "submitEditing");
  await fireEvent(confirmField, "submitEditing");
  release();
  await screen.findByText(/Нууц үг солигдож/);
  expect(calls("POST /api/v1/auth/password")).toHaveLength(1);
});

test("dates are shown in Ulaanbaatar time as YYYY.MM.DD HH:mm", () => {
  const { formatDate, formatDateTime } =
    jest.requireActual<typeof import("@/lib/dates")>("@/lib/dates");
  expect(formatDateTime("2026-11-01T03:00:00Z")).toBe("2026.11.01 11:00");
  expect(formatDate("2026-12-31T20:30:00Z")).toBe("2027.01.01"); // already the next day in UB
});
