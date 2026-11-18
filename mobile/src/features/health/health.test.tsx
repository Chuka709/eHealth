import { fireEvent, renderRouter, screen, waitFor } from "expo-router/testing-library";
import { Alert } from "react-native";

import { clearAccessToken, setStatus } from "@/features/auth/session-store";
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
const allGiven = ["terms", "privacy", "sensitive_data", "ai_processing", "cross_border"].map(
  (kind) => ({
    kind,
    current_version: "draft-2026-10",
    granted: kind !== "ai_processing" && kind !== "cross_border",
    granted_version: "draft-2026-10",
    at: "2026-10-01T00:00:00Z",
    required: !["ai_processing", "cross_border"].includes(kind),
  }),
);
const P = `/api/v1/patients/${OWN.id}`;
let store: Record<string, Record<string, unknown>[]> = {};
let posts: { path: string; body: Record<string, unknown> }[] = [];
let vitalStatus = 201;

const handlers: Record<string, Handler> = {
  "POST /api/v1/auth/refresh": () =>
    json(200, { access_token: "a1", token_type: "bearer", expires_in: 900, refresh_token: "r1" }),
  "GET /api/v1/me": () => json(200, { locale: "mn", display_name: "Бат Болд" }),
  "GET /api/v1/me/consents": () => json(200, allGiven),
  "GET /api/v1/me/notifications": () => json(200, []),
  "GET /api/v1/healthz": () => json(200, { status: "ok" }),
  "GET /api/v1/patients": () => json(200, [OWN]),
  [`GET ${P}/transplants`]: () => json(200, []),
  [`GET ${P}/medications`]: () => json(200, []),
  [`GET ${P}/timezone`]: () =>
    json(200, { home: "Asia/Ulaanbaatar", current: "Asia/Ulaanbaatar", switches: [] }),
  [`GET ${P}/vitals`]: () => json(200, store.vitals ?? []),
};
for (const kind of ["events", "allergies", "contacts", "appointments", "questions"]) {
  handlers[`GET ${P}/${kind}`] = () => json(200, store[kind] ?? []);
  handlers[`POST ${P}/${kind}`] = async (request) => {
    const body = (await request.json()) as Record<string, unknown>;
    posts.push({ path: kind, body });
    const row = { ...body, id: `id-${posts.length}`, created_at: "", updated_at: null };
    store[kind] = [...(store[kind] ?? []), row];
    return json(201, row);
  };
}
let nka: string | null = null;
handlers[`GET ${P}/no-known-allergies`] = () => json(200, { confirmed_on: nka });
handlers[`PUT ${P}/no-known-allergies`] = () => {
  nka = "2026-11-18";
  return json(200, { confirmed_on: nka });
};
handlers[`DELETE ${P}/no-known-allergies`] = () => {
  nka = null;
  return new Response(null, { status: 204 });
};
handlers[`POST ${P}/vitals`] = async (request) => {
  const body = (await request.json()) as Record<string, unknown>;
  posts.push({ path: "vitals", body });
  if (vitalStatus !== 201) {
    return json(vitalStatus, { code: "vital.implausible", message_key: "error.vital.implausible" });
  }
  return json(201, []);
};

beforeEach(() => {
  queryClient.clear();
  clearAccessToken();
  setStatus("loading");
  mockStore.clear();
  mockStore.set("lt.refresh", "r0");
  mockStore.set("lt.account", "00000000-0000-4000-8000-000000000001");
  store = {};
  posts = [];
  vitalStatus = 201;
  nka = null;
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

async function openProfile() {
  await renderRouter("./src/app", { initialUrl: "/" });
  await fireEvent.press(await screen.findByRole("button", { name: /^Профайл/ }));
}

const press = async (name: string | RegExp) =>
  fireEvent.press(await screen.findByRole(/button|radio|link|checkbox/, { name }));

test("the profile lists every part, with allergies by name", async () => {
  store.allergies = [
    {
      id: "a1",
      substance: "Пенициллин",
      reaction: null,
      severity: "severe",
      noted_on: null,
      created_at: "",
      updated_at: null,
    },
  ];
  await openProfile();
  expect(await screen.findByTestId("profile-appointments")).toBeOnTheScreen();
  for (const id of ["vitals", "contacts", "questions", "events", "transplants"]) {
    expect(screen.getByTestId(`profile-${id}`)).toBeOnTheScreen();
  }
  expect(await screen.findByText("Пенициллин")).toBeOnTheScreen();
});

test("an allergy is added with the form's client_id; a missing substance is said", async () => {
  await openProfile();
  await fireEvent.press(await screen.findByTestId("profile-allergies"));
  await press("Харшил нэмэх");
  await press("Хадгалах");
  expect(await screen.findByText("Тэмдэглэсэн талбаруудыг засна уу.")).toBeOnTheScreen();
  expect(posts).toHaveLength(0);
  await fireEvent.changeText(await screen.findByLabelText("Юунд харшилтай вэ"), "Пенициллин");
  await press("Хүнд");
  await press("Хадгалах");
  await waitFor(() => expect(posts).toHaveLength(1));
  expect(posts[0].body).toMatchObject({ substance: "Пенициллин", severity: "severe" });
  expect(String(posts[0].body.client_id)).toMatch(/^[0-9a-f-]{36}$/);
});

test("no known allergies is confirmed on purpose, dated, and offered only with none recorded (Q39)", async () => {
  const asked = jest.spyOn(Alert, "alert").mockImplementation((_t, _m, buttons) => {
    buttons?.find((b) => b.style !== "cancel")?.onPress?.();
  });
  await openProfile();
  await fireEvent.press(await screen.findByTestId("profile-allergies"));
  // none recorded is not "no allergies" (H17)
  expect(await screen.findByText(/^Харшил бүртгээгүй нь харшилгүй гэсэн үг биш/)).toBeOnTheScreen();
  await press("Мэдэгдэж буй харшилгүй гэж батлах");
  expect(asked).toHaveBeenCalledTimes(1);
  expect(
    await screen.findByText(/^Мэдэгдэж буй харшилгүй гэж баталсан \(2026\.11\.18\)/),
  ).toBeOnTheScreen();
  await press("Баталгааг цуцлах");
  expect(await screen.findByText(/^Харшил бүртгээгүй нь харшилгүй/)).toBeOnTheScreen();
  asked.mockRestore();
});

test("with an allergy recorded, no known allergies is not offered", async () => {
  store.allergies = [
    {
      id: "a1",
      substance: "Пенициллин",
      reaction: null,
      severity: null,
      noted_on: null,
      created_at: "",
      updated_at: null,
    },
  ];
  nka = "2026-11-01"; // a stale answer never shows beside an allergy
  await openProfile();
  await fireEvent.press(await screen.findByTestId("profile-allergies"));
  expect(await screen.findByText("Пенициллин")).toBeOnTheScreen();
  expect(screen.queryByText(/Мэдэгдэж буй харшилгүй/)).toBeNull();
});

test("a contact's phone is checked before it is sent", async () => {
  await openProfile();
  await fireEvent.press(await screen.findByTestId("profile-contacts"));
  await press("Холбоо барих хүн нэмэх");
  await fireEvent.changeText(await screen.findByLabelText("Нэр"), "Дорж");
  await fireEvent.changeText(screen.getByLabelText("Утас"), "99");
  await press("Хадгалах");
  expect(await screen.findByText(/Утасны дугаар буруу байна/)).toBeOnTheScreen();
  await fireEvent.changeText(screen.getByLabelText("Утас"), "+976 9911 2233");
  await press("Хадгалах");
  await waitFor(() => expect(posts).toHaveLength(1));
  expect(posts[0].body).toMatchObject({ name: "Дорж", phone: "+976 9911 2233" });
});

test("blood pressure is one reading with the unit in every label", async () => {
  await openProfile();
  await fireEvent.press(await screen.findByTestId("profile-vitals"));
  await press("Хэмжилт нэмэх");
  await press("Даралт");
  await fireEvent.changeText(await screen.findByLabelText("Дээд даралт (мм МУБ)"), "128");
  await fireEvent.changeText(screen.getByLabelText("Доод даралт (мм МУБ)"), "82");
  await press("Хадгалах");
  await waitFor(() => expect(posts).toHaveLength(1));
  expect(posts[0].body.items).toEqual([
    { kind: "bp_systolic", value: "128" },
    { kind: "bp_diastolic", value: "82" },
  ]);
});

test("a refused reading is said at once (online)", async () => {
  vitalStatus = 422;
  await openProfile();
  await fireEvent.press(await screen.findByTestId("profile-vitals"));
  await press("Хэмжилт нэмэх");
  await press("Жин");
  await fireEvent.changeText(await screen.findByLabelText("Жин (кг)"), "700");
  await press("Хадгалах");
  expect(await screen.findByText(/буруу бичигдсэн байж магадгүй/)).toBeOnTheScreen();
});

test("glucose asks the meter's unit first; mg/dL is never taken (H26)", async () => {
  await openProfile();
  await fireEvent.press(await screen.findByTestId("profile-vitals"));
  await press("Хэмжилт нэмэх");
  await press("Цусан дахь сахар");
  expect(
    await screen.findByText("Таны сахар хэмжигч ямар нэгжээр харуулдаг вэ?"),
  ).toBeOnTheScreen();
  expect(screen.queryByLabelText("Цусан дахь сахар (ммоль/л)")).toBeNull();
  await press(/^мг\/дл/);
  expect(await screen.findByText(/зөвхөн ммоль\/л-ээр хадгална/)).toBeOnTheScreen();
  expect(screen.queryByLabelText("Цусан дахь сахар (ммоль/л)")).toBeNull();
  await press(/^ммоль\/л/);
  expect(await screen.findByLabelText("Цусан дахь сахар (ммоль/л)")).toBeOnTheScreen();
});

test("an edit without a network says so at once and keeps the draft", async () => {
  const { onlineManager } = jest.requireActual("@tanstack/react-query") as {
    onlineManager: { setOnline: (on: boolean) => void };
  };
  await openProfile();
  await fireEvent.press(await screen.findByTestId("profile-allergies"));
  await press("Харшил нэмэх");
  await fireEvent.changeText(await screen.findByLabelText("Юунд харшилтай вэ"), "Пенициллин");
  onlineManager.setOnline(false);
  try {
    await press("Хадгалах");
    expect(await screen.findByText(/Сервертэй холбогдож чадсангүй/)).toBeOnTheScreen();
    expect(posts).toHaveLength(0);
    expect(screen.getByLabelText("Юунд харшилтай вэ").props.value).toBe("Пенициллин");
  } finally {
    onlineManager.setOnline(true);
  }
});

test("an appointment is reminded a day and two hours before, without its name (H10)", async () => {
  const os = (
    jest.requireMock("expo-notifications") as {
      __scheduled: Map<string, { identifier: string; content: { title: string; body: string } }>;
    }
  ).__scheduled;
  os.clear();
  const at = new Date(Date.now() + 3 * 86_400_000);
  at.setSeconds(0, 0);
  store.appointments = [
    {
      id: "11111111-1111-4111-8111-111111111111",
      kind: "biopsy",
      title: "Бөөрний биопси",
      scheduled_at: at.toISOString(),
      place: "Улсын нэгдүгээр төв эмнэлэг",
      notes: null,
      reminder_offsets_min: [1440, 120],
      status: "planned",
      created_at: "",
      updated_at: null,
    },
  ];
  await openProfile();
  await waitFor(() => expect([...os.keys()].filter((k) => k.startsWith("appt."))).toHaveLength(2));
  for (const n of [...os.values()].filter((v) => v.identifier.startsWith("appt."))) {
    expect(n.content.title).toBe("Танд товлол байна");
    expect(JSON.stringify(n.content)).not.toMatch(/биопси|эмнэлэг/i);
  }
});
