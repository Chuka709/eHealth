import { fireEvent, renderRouter, screen, waitFor } from "expo-router/testing-library";
import { Alert, type AlertButton } from "react-native";

import { getNotice, setNotice } from "@/features/auth/notice";
import { clearAccessToken, getStatus, setStatus } from "@/features/auth/session-store";
import { setBiometricOn, setLocked } from "@/features/lock/lock-store";
import { apiBaseUrl } from "@/lib/api-base";
import { setLocale } from "@/lib/i18n";
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
  SecurityLevel: { BIOMETRIC_STRONG: 3 },
  getEnrolledLevelAsync: jest.fn(async () => 0),
}));
jest.mock("@/lib/support", () => ({ supportPhone: "7011 0000", supportPhoneUrl: "tel:70110000" }));

type Handler = (request: Request) => Promise<Response> | Response;
const mockFetch = jest.fn<Promise<Response>, [Request]>();
const json = (status: number, body: unknown) =>
  new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
const err = (status: number, code: string) => json(status, { code, message_key: `error.${code}` });
const noContent = () => new Response(null, { status: 204 });

const KINDS = ["terms", "privacy", "sensitive_data", "ai_processing", "cross_border"] as const;
type Kind = (typeof KINDS)[number];
let given: Partial<Record<Kind, boolean>> = {};
const consents = () =>
  KINDS.map((kind) => ({
    kind,
    current_version: "draft-2026-10",
    granted: given[kind] === true,
    granted_version: given[kind] === undefined ? null : "draft-2026-10",
    at: given[kind] ? "2026-10-01T02:00:00Z" : null,
    required: ["terms", "privacy", "sensitive_data"].includes(kind),
  }));
let notifications: unknown[] = [];

const sent: [string, string][] = [];
const bodies = (key: string) =>
  sent.filter(([k]) => k === key).map(([, text]) => (text ? JSON.parse(text) : null));
const calls = (key: string) => sent.filter(([k]) => k === key);

function route(extra: Record<string, Handler> = {}) {
  const handlers: Record<string, Handler> = {
    "POST /api/v1/auth/refresh": () =>
      json(200, { access_token: "a1", token_type: "bearer", expires_in: 900, refresh_token: "r1" }),
    "GET /api/v1/me/consents": () => json(200, consents()),
    "POST /api/v1/me/consents": async (request) => {
      const body = (await request.clone().json()) as { items: { kind: Kind; granted: boolean }[] };
      for (const i of body.items) given[i.kind] = i.granted;
      return noContent();
    },
    "GET /api/v1/me": () => json(200, { locale: "mn", username: "bat.01", display_name: "Бат" }),
    "GET /api/v1/me/notifications": () => json(200, notifications),
    "POST /api/v1/me/notifications/7/read": () => {
      notifications = [];
      return noContent();
    },
    "GET /api/v1/me/admin-actions": () =>
      json(200, [
        { at: "2026-11-01T03:00:00Z", action: "admin.token_issue", actor_role: "super_admin" },
        { at: "2026-10-01T01:00:00Z", action: "admin.something_new", actor_role: "support" },
      ]),
    "POST /api/v1/me/report-unwanted-admin-action": noContent,
    "POST /api/v1/me/delete": () => json(202, { scheduled_for: "2026-12-03T16:30:00Z" }),
    "POST /api/v1/auth/logout": noContent,
    "GET /api/v1/healthz": () => json(200, { status: "ok" }),
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

const alert = jest.spyOn(Alert, "alert");
const confirm = (text: string) => {
  const buttons = alert.mock.calls.at(-1)?.[2] as AlertButton[] | undefined;
  buttons?.find((b) => b.text === text)?.onPress?.();
};

beforeEach(() => {
  queryClient.clear();
  clearAccessToken();
  setStatus("loading");
  setNotice(null);
  setLocked(false);
  setBiometricOn(false);
  setLocale("mn");
  alert.mockClear();
  mockStore.clear();
  mockStore.set("lt.refresh", "r0");
  mockStore.set("lt.device", "d0");
  mockStore.set("lt.biometric", "off");
  given = { terms: true, privacy: true, sensitive_data: true };
  notifications = [];
  sent.length = 0;
  mockFetch.mockReset();
  globalThis.fetch = mockFetch as unknown as typeof fetch;
  route();
});

const open = () => renderRouter("./src/app", { initialUrl: "/" });
const openSettingsRow = async (testID: string) => {
  await open();
  await fireEvent.press(await screen.findByRole("button", { name: "Тохиргоо" }));
  await fireEvent.press(await screen.findByTestId(testID));
};

describe("admin changes on Home (docs/04 §1 step 5c)", () => {
  beforeEach(() => {
    notifications = [
      {
        id: 7,
        kind: "admin_reset",
        title_key: "account.admin_reset",
        created_at: "2026-11-02T04:15:00Z",
        read_at: null,
      },
    ];
  });

  test("shows what was done and when; 'this was my request' marks it read", async () => {
    await open();
    expect(await screen.findByText(/Таны аккаунтад админ өөрчлөлт хийсэн/)).toBeOnTheScreen();
    expect(
      screen.getByText("Админ таны нууц үгийг шинэчлэх код олгосон — 2026.11.02 12:15"),
    ).toBeOnTheScreen();
    await fireEvent.press(screen.getByRole("button", { name: "Энэ миний хүсэлтээр болсон" }));
    await waitFor(() => expect(screen.queryByText(/админ өөрчлөлт хийсэн/)).toBeNull());
    expect(calls("POST /api/v1/me/notifications/7/read")).toHaveLength(1);
  });

  test("'I didn't ask for this' locks the account, wipes the phone and keeps the notice", async () => {
    await open();
    await fireEvent.press(
      await screen.findByRole("button", { name: "Би хүсээгүй — аккаунтаа түгжих" }),
    );
    expect(calls("POST /api/v1/me/report-unwanted-admin-action")).toHaveLength(0); // asks first
    confirm("Түгжих");
    expect(await screen.findByText("Аккаунт тань түгжигдлээ")).toBeOnTheScreen();
    expect(screen.getByText(/7011 0000 руу залгаж/)).toBeOnTheScreen();
    for (const key of ["lt.refresh", "lt.device", "lt.biometric"]) {
      expect(mockStore.has(key)).toBe(false);
    }
    expect(JSON.parse(mockStore.get("lt.notice") ?? "null")).toEqual({ kind: "reported" });

    await fireEvent.press(screen.getByRole("button", { name: "Ойлголоо" }));
    expect(await screen.findByText("LabTrack MN-д тавтай морил")).toBeOnTheScreen();
    expect(mockStore.has("lt.notice")).toBe(false);
  });

  test("outside the 30 days the report is refused and the session stays", async () => {
    route({
      "POST /api/v1/me/report-unwanted-admin-action": () => err(409, "me.no_recent_admin_action"),
    });
    await open();
    await fireEvent.press(
      await screen.findByRole("button", { name: "Би хүсээгүй — аккаунтаа түгжих" }),
    );
    confirm("Түгжих");
    expect(await screen.findByText(/Сүүлийн 30 хоногт админы үйлдэл алга/)).toBeOnTheScreen();
    expect(getStatus()).toBe("signedIn");
  });
});

test("admin history: what, when (UB time) and the role — never who", async () => {
  await openSettingsRow("settings-admin-history");
  expect(
    await screen.findByText("Идэвхжүүлэх эсвэл нууц үг шинэчлэх код олгосон"),
  ).toBeOnTheScreen();
  expect(screen.getByText("2026.11.01 11:00 · Супер админ")).toBeOnTheScreen();
  expect(screen.getByText("Админы бусад үйлдэл")).toBeOnTheScreen(); // unknown action
  expect(screen.getByRole("button", { name: "Би хүсээгүй — аккаунтаа түгжих" })).toBeOnTheScreen();
});

describe("account deletion", () => {
  test("needs the password, asks again, then wipes the phone and shows the date", async () => {
    await openSettingsRow("settings-delete-account");
    const submit = await screen.findByRole("button", { name: "Аккаунтаа устгах" });
    await fireEvent.press(submit);
    expect(await screen.findByText(/Энэ талбарыг бөглөнө үү/)).toBeOnTheScreen();

    await fireEvent.changeText(screen.getByLabelText("Нууц үгээрээ баталгаажуулна уу"), "pw-1");
    await fireEvent.press(submit);
    expect(calls("POST /api/v1/me/delete")).toHaveLength(0); // second confirmation first
    confirm("Устгах");

    expect(await screen.findByText("Устгах хүсэлтийг хүлээн авлаа")).toBeOnTheScreen();
    expect(screen.getByText(/2026\.12\.04-нд бүрмөсөн устна/)).toBeOnTheScreen(); // UB date
    expect(bodies("POST /api/v1/me/delete")).toEqual([{ password: "pw-1" }]);
    for (const key of ["lt.refresh", "lt.device", "lt.biometric"]) {
      expect(mockStore.has(key)).toBe(false);
    }
    expect(getNotice()).toEqual({ kind: "deleted", scheduledFor: "2026-12-03T16:30:00Z" });
  });

  test("a wrong password stays on the field, is cleared, and nothing is wiped", async () => {
    route({ "POST /api/v1/me/delete": () => err(401, "auth.invalid_credentials") });
    await openSettingsRow("settings-delete-account");
    const field = await screen.findByLabelText("Нууц үгээрээ баталгаажуулна уу");
    await fireEvent.changeText(field, "wrong");
    await fireEvent.press(screen.getByRole("button", { name: "Аккаунтаа устгах" }));
    confirm("Устгах");
    expect(await screen.findByText(/Нууц үг буруу байна/)).toBeOnTheScreen();
    expect(screen.getByLabelText("Нууц үгээрээ баталгаажуулна уу").props.value).toBe("");
    expect(getStatus()).toBe("signedIn");
    expect(mockStore.get("lt.refresh")).toBe("r1");
  });
});

describe("consents in Settings", () => {
  test("withdrawing a required consent asks first, then the consents screen takes over", async () => {
    await openSettingsRow("settings-consents");
    await fireEvent.press(
      await screen.findByRole("button", { name: "«Үйлчилгээний нөхцөл» зөвшөөрлийг татах" }),
    );
    expect(calls("POST /api/v1/me/consents")).toHaveLength(0);
    confirm("Татах");
    expect(await screen.findByText(/доорх нөхцөлүүдийг уншаад зөвшөөрнө үү/)).toBeOnTheScreen();
    expect(bodies("POST /api/v1/me/consents")).toEqual([
      { items: [{ kind: "terms", granted: false, version: "draft-2026-10" }] },
    ]);
  });

  test("the AI switch gives and withdraws both parts together", async () => {
    await openSettingsRow("settings-consents");
    await fireEvent(await screen.findByTestId("consent-settings-ai"), "valueChange", true);
    await waitFor(() => expect(calls("POST /api/v1/me/consents")).toHaveLength(1));
    expect(bodies("POST /api/v1/me/consents")[0]).toEqual({
      items: [
        { kind: "ai_processing", granted: true, version: "draft-2026-10" },
        { kind: "cross_border", granted: true, version: "draft-2026-10" },
      ],
    });
  });
});

test("an old notice (over 30 days) offers no report the server would refuse", async () => {
  notifications = [
    {
      id: 7,
      kind: "admin_action",
      title_key: "account.identity_set",
      created_at: new Date(Date.now() - 40 * 86_400_000).toISOString(),
      read_at: null,
    },
  ];
  await open();
  expect(await screen.findByText(/Админ таны РД-г бүртгэсэн/)).toBeOnTheScreen();
  expect(screen.queryByRole("button", { name: "Би хүсээгүй — аккаунтаа түгжих" })).toBeNull();
});

test("an unknown notice title is shown generically, never as a raw key", async () => {
  notifications = [
    {
      id: 7,
      kind: "admin_action",
      title_key: "account",
      created_at: new Date().toISOString(),
      read_at: null,
    },
  ];
  await open();
  expect(await screen.findByText(/Админ таны аккаунтад өөрчлөлт хийсэн —/)).toBeOnTheScreen();
});

test("an unreadable stored notice shows a neutral text, not a false admin reset", async () => {
  mockStore.delete("lt.refresh");
  mockStore.set("lt.notice", "{not json");
  await open();
  expect(await screen.findByText("LabTrack MN-д тавтай морил")).toBeOnTheScreen();
  expect(screen.queryByText(/админ шинэчилсэн/)).toBeNull();
});

test("the AI switch shows on while one part is still given, and off withdraws both", async () => {
  given = {
    terms: true,
    privacy: true,
    sensitive_data: true,
    ai_processing: true,
    cross_border: false,
  };
  await openSettingsRow("settings-consents");
  const ai = await screen.findByTestId("consent-settings-ai");
  expect(ai.props.isOn).toBe(true); // the native switch's own prop
  await fireEvent(ai, "valueChange", false);
  await waitFor(() => expect(calls("POST /api/v1/me/consents")).toHaveLength(1));
  expect(bodies("POST /api/v1/me/consents")[0]).toEqual({
    items: [
      { kind: "ai_processing", granted: false, version: "draft-2026-10" },
      { kind: "cross_border", granted: false, version: "draft-2026-10" },
    ],
  });
});

test("a lost report response: the refresh tells why and the notice still appears", async () => {
  notifications = [
    {
      id: 7,
      kind: "admin_reset",
      title_key: "account.admin_reset",
      created_at: new Date().toISOString(),
      read_at: null,
    },
  ];
  let refreshes = 0;
  route({
    "POST /api/v1/me/report-unwanted-admin-action": () => {
      throw new TypeError("Network request failed"); // the server did it; the answer is lost
    },
    "POST /api/v1/auth/refresh": () =>
      ++refreshes === 1
        ? json(200, {
            access_token: "a1",
            token_type: "bearer",
            expires_in: 900,
            refresh_token: "r1",
          })
        : err(401, "auth.account_reported"),
  });
  await open();
  await fireEvent.press(
    await screen.findByRole("button", { name: "Би хүсээгүй — аккаунтаа түгжих" }),
  );
  confirm("Түгжих");
  expect(await screen.findByText("Аккаунт тань түгжигдлээ")).toBeOnTheScreen();
});

test("a deletion learnt from a refresh shows the notice without a date", async () => {
  route({ "POST /api/v1/auth/refresh": () => err(401, "auth.deletion_pending") });
  await open();
  expect(await screen.findByText("Устгах хүсэлтийг хүлээн авлаа")).toBeOnTheScreen();
  expect(screen.getByText(/хүсэлт гаргаснаас хойш 30 хоногийн дараа/)).toBeOnTheScreen();
});
