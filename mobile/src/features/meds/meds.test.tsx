import { fireEvent, renderRouter, screen, waitFor } from "expo-router/testing-library";

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
const MED_ID = "22222222-2222-4222-8222-222222222222";
const regimen = (id: string, from: string, times: { at: string; amount: string }[]) => ({
  id,
  effective_from: from,
  dose_amount: null,
  dose_unit: "mg",
  dose_unit_text: null,
  schedule: { type: "daily", times },
  instructions: null,
  changed_by_note: null,
  voided_at: null,
  void_reason: null,
  created_at: "2026-01-01T00:00:00Z",
});
const TACROLIMUS = {
  id: MED_ID,
  catalog_code: "TACROLIMUS",
  category: "immunosuppressant",
  name: "Такролимус",
  brand: null,
  form: "капсул",
  strength: "1 мг",
  route: "oral",
  purpose: null,
  prescribed_by: null,
  transplant_id: null,
  started_on: "2026-01-01",
  stopped_on: null,
  stop_reason: null,
  planned_end_on: null,
  is_long_term: true,
  reminders_enabled: true,
  reminder_timezone_mode: "home",
  notes: null,
  is_current: true,
  current_regimen: regimen("33333333-3333-4333-8333-333333333333", "2026-01-01", [
    { at: "08:00", amount: "2" },
    { at: "20:00", amount: "1.5" },
  ]),
  next_regimen: null,
  regimens: [] as unknown[],
  created_at: "2026-01-01T00:00:00Z",
  updated_at: null,
};
TACROLIMUS.regimens = [TACROLIMUS.current_regimen];

let medications: Record<string, unknown>[] = [];
let refuseIntakes = false;
let deleted: string[] = [];
let posts: { key: string; body: Record<string, unknown> }[] = [];

const handlers: Record<string, Handler> = {
  "POST /api/v1/auth/refresh": () =>
    json(200, { access_token: "a1", token_type: "bearer", expires_in: 900, refresh_token: "r1" }),
  "GET /api/v1/me": () => json(200, { locale: "mn", display_name: "Бат Болд" }),
  "GET /api/v1/me/consents": () => json(200, allGiven),
  "GET /api/v1/me/notifications": () => json(200, []),
  "GET /api/v1/healthz": () => json(200, { status: "ok" }),
  "GET /api/v1/patients": () => json(200, [OWN]),
  [`GET /api/v1/patients/${OWN.id}/transplants`]: () => json(200, []),
  [`GET /api/v1/patients/${OWN.id}/medications`]: () => json(200, medications),
  [`GET /api/v1/patients/${OWN.id}/timezone`]: () =>
    json(200, { home: "Asia/Ulaanbaatar", current: "Asia/Ulaanbaatar", switches: [] }),
  [`GET /api/v1/patients/${OWN.id}/intakes`]: () =>
    json(
      200,
      posts
        .filter((p) => p.key === "intake")
        .map((p) => ({
          ...p.body,
          id: `9${String(p.body.client_id).slice(1)}`, // the server's own id, not client_id
          note: null,
          created_at: "",
          updated_at: null,
        })),
    ),
  [`GET /api/v1/patients/${OWN.id}/adherence`]: () =>
    json(200, {
      month: "2026-11",
      total: { planned: 8, taken: 6, skipped: 1, unrecorded: 0, open: 1, percent_taken: "85" },
      medications: [],
    }),
  "GET /api/v1/medication-catalog": () =>
    json(200, [
      {
        code: "TACROLIMUS",
        generic_mn: "Такролимус",
        generic_en: "Tacrolimus",
        brands: ["Prograf", "Advagraf"],
        category: "immunosuppressant",
        forms: ["капсул"],
      },
    ]),
  [`POST /api/v1/patients/${OWN.id}/intakes`]: async (request) => {
    const body = (await request.json()) as Record<string, unknown>;
    if (refuseIntakes) return json(422, { code: "validation", message_key: "error.validation" });
    posts.push({ key: "intake", body });
    return json(201, { ...body, id: body.client_id, note: null, created_at: "", updated_at: null });
  },
  [`POST /api/v1/patients/${OWN.id}/medications`]: async (request) => {
    const body = (await request.json()) as Record<string, unknown>;
    posts.push({ key: "medication", body });
    return json(201, TACROLIMUS);
  },
};

beforeEach(() => {
  queryClient.clear();
  clearAccessToken();
  setStatus("loading");
  mockStore.clear();
  mockStore.set("lt.refresh", "r0");
  mockStore.set("lt.account", "00000000-0000-4000-8000-000000000001");
  medications = [TACROLIMUS];
  posts = [];
  refuseIntakes = false;
  deleted = [];
  mockFetch.mockReset();
  mockFetch.mockImplementation(async (input: Request | string, init?: RequestInit) => {
    const request = typeof input === "string" ? new Request(input, init) : input;
    const path = request.url.slice(apiBaseUrl.length).split("?")[0];
    if (request.method === "DELETE" && path.startsWith(`/api/v1/patients/${OWN.id}/intakes/`)) {
      deleted.push(path.split("/").at(-1) ?? "");
      posts = posts.filter(
        (p) => `9${String(p.body.client_id).slice(1)}` !== path.split("/").at(-1),
      );
      return new Response(null, { status: 204 });
    }
    const handler = handlers[`${request.method} ${path}`];
    if (!handler) return json(404, { code: "not_found", message_key: "error.not_found" });
    return handler(request);
  });
  globalThis.fetch = mockFetch as unknown as typeof fetch;
});

afterEach(() => queryClient.clear());

async function openMeds() {
  await renderRouter("./src/app", { initialUrl: "/" });
  await fireEvent.press(await screen.findByRole("button", { name: /^Эм/ }));
}

const press = async (name: string | RegExp) =>
  fireEvent.press(await screen.findByRole(/button|radio|link|checkbox/, { name }));

test("today's doses come from the dose history; a tap records one through the queue", async () => {
  await openMeds();
  const morning = await screen.findByTestId(`dose-${MED_ID}-08:00`);
  expect(morning).toBeOnTheScreen();
  expect(screen.getByTestId(`dose-${MED_ID}-20:00`)).toBeOnTheScreen();
  // a dose whose time has passed reads "not recorded", a coming one "not yet due" - never missed
  expect(screen.getAllByText(/^(Тэмдэглээгүй|Цаг нь болоогүй)$/)).toHaveLength(2);
  // the monthly counts: plain numbers, nothing called missed
  expect(
    await screen.findByText("Уусан гэж тэмдэглэсэн: 6 / товлосон тун: 8 (85%)."),
  ).toBeOnTheScreen();
  expect(screen.queryByText(/алдсан|мартсан/)).toBeNull();

  const [taken] = screen.getAllByRole("button", { name: /^Уусан — / });
  await fireEvent.press(taken);
  await waitFor(() => expect(posts.filter((p) => p.key === "intake")).toHaveLength(1));
  const body = posts[0].body;
  expect(body).toMatchObject({ medication_id: MED_ID, status: "taken" });
  // the dose's own minute (08:00 Ulaanbaatar), not the moment of the tap
  expect(new Date(String(body.scheduled_at)).toISOString()).toMatch(/T00:00:00\.000Z$/);
  expect(String(body.client_id)).toMatch(/^[0-9a-f-]{36}$/);
  expect(await screen.findByText("✓ Уусан гэж тэмдэглэсэн")).toBeOnTheScreen();
});

test("adding a medicine: catalog search, a dose per time, ambiguous numbers refused", async () => {
  medications = [];
  await openMeds();
  await press("Эм нэмэх");
  await fireEvent.changeText(await screen.findByLabelText("Эмийн нэрээр хайх"), "так");
  await press(/Такролимус · Prograf/);
  expect(await screen.findByText("Сонгосон: Такролимус")).toBeOnTheScreen();

  await fireEvent.changeText(screen.getByLabelText("1-р цагийн тун"), "1,000");
  await press("Хадгалах");
  expect(await screen.findByText(/1,000 мэт мянгатын тусгаарлагч/)).toBeOnTheScreen();
  expect(await screen.findByText("Нэгжээ сонгоно уу.")).toBeOnTheScreen();
  expect(posts).toHaveLength(0);

  await fireEvent.changeText(screen.getByLabelText("1-р цагийн тун"), "2");
  await press("Цаг нэмэх");
  await fireEvent.changeText(await screen.findByLabelText("2-р цагийн тун"), "1,5");
  await press("Нэгж: Сонгоогүй");
  await press("мг");
  await press("Хадгалах");
  await waitFor(() => expect(posts).toHaveLength(1));
  expect(posts[0].body).toMatchObject({
    catalog_code: "TACROLIMUS",
    name: "Такролимус",
    form: "капсул",
    reminders_enabled: true,
    reminder_timezone_mode: "home",
    regimen: {
      dose_unit: "mg",
      schedule: {
        type: "daily",
        times: [
          { at: "08:00", amount: "2" },
          { at: "09:00", amount: "1,5" },
        ],
      },
    },
  });
});

test("a dose change always asks from when (H8)", async () => {
  await openMeds();
  await press(/Такролимус 1 мг/);
  expect(await screen.findByText("Тунгийн түүх")).toBeOnTheScreen();
  await press("Тун өөрчлөх");
  expect(await screen.findByText(/Хуучин тун түүхэнд хадгалагдана/)).toBeOnTheScreen();
  // the form starts from the current dose; the date is never preset
  expect(screen.getByLabelText("1-р цагийн тун (мг)").props.value).toBe("2");
  expect(screen.getByRole("button", { name: "Шинэ тун хэзээнээс: Сонгоогүй" })).toBeOnTheScreen();
  await press("Хадгалах");
  expect(await screen.findByText("Тэмдэглэсэн талбаруудыг засна уу.")).toBeOnTheScreen();
  expect(posts).toHaveLength(0);
});

test("a recorded dose can be undone; a refused one is shown, never dropped", async () => {
  await openMeds();
  await screen.findByTestId(`dose-${MED_ID}-08:00`);
  const [taken] = screen.getAllByRole("button", { name: /^Уусан — / });
  await fireEvent.press(taken);
  expect(await screen.findByText("✓ Уусан гэж тэмдэглэсэн")).toBeOnTheScreen();
  // sent already: undone on the server, by the stored row's own id
  await waitFor(() => expect(screen.getByRole("link", { name: /^Буцаах — / })).toBeEnabled());
  await press(/^Буцаах — /);
  await waitFor(() => expect(deleted).toHaveLength(1));
  expect(deleted[0]).toMatch(/^9/);
  await waitFor(() => expect(screen.queryByText("✓ Уусан гэж тэмдэглэсэн")).toBeNull());

  refuseIntakes = true;
  const [skip] = screen.getAllByRole("button", { name: /^Алгассан — / });
  await fireEvent.press(skip);
  expect(await screen.findByTestId("failed-doses")).toBeOnTheScreen();
  expect(screen.getByText(/сервер хүлээж аваагүй/)).toBeOnTheScreen();
  await press("Ойлголоо");
  await waitFor(() => expect(screen.queryByTestId("failed-doses")).toBeNull());
});
