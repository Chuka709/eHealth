import { fireEvent, renderRouter, screen, waitFor } from "expo-router/testing-library";
import { Alert } from "react-native";

import { clearAccessToken, setStatus } from "@/features/auth/session-store";
import { apiBaseUrl } from "@/lib/api-base";
import { queryClient } from "@/lib/query-client";

// Home (Phase 2.9). The fixtures follow features/meds/meds.test.tsx.

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

let transplants: Record<string, unknown>[] = [];
let appointments: Record<string, unknown>[] = [];
handlers[`GET /api/v1/patients/${OWN.id}/transplants`] = () => json(200, transplants);
handlers[`GET /api/v1/patients/${OWN.id}/appointments`] = () => json(200, appointments);

const transplant = (over: Record<string, unknown>) => ({
  id: "44444444-4444-4444-8444-444444444441",
  organ: "kidney",
  organ_detail: null,
  transplant_date: "2019-05-12",
  date_precision: "day",
  country: "KR",
  city: null,
  hospital: "Asan Medical Center",
  transplant_number: 1,
  donor_type: "living_related",
  graft_status: "functioning",
  elapsed: { days: 0, months: 77, years: 6, approximate: false },
  created_at: "2026-01-01T00:00:00Z",
  updated_at: null,
  ...over,
});
const appointment = (id: string, at: string, over: Record<string, unknown> = {}) => ({
  id,
  kind: "clinic_visit",
  title: `Үзлэг ${id}`,
  scheduled_at: at,
  place: null,
  notes: null,
  reminder_offsets_min: [],
  status: "planned",
  created_at: "2026-01-01T00:00:00Z",
  updated_at: null,
  ...over,
});
const inDays = (days: number) => new Date(Date.now() + days * 86_400_000).toISOString();

beforeEach(() => {
  transplants = [];
  appointments = [];
});

const openHome = async () => renderRouter("./src/app", { initialUrl: "/" });

test("Home: the latest transplant with the server's time since, opening its record", async () => {
  transplants = [
    transplant({}),
    transplant({
      id: "44444444-4444-4444-8444-444444444442",
      transplant_date: "2024-03-01",
      date_precision: "month",
      hospital: "ШУТИС",
      transplant_number: 2,
      graft_status: "unknown",
      elapsed: { days: 0, months: 32, years: 2, approximate: true },
    }),
  ];
  await openHome();
  const card = await screen.findByTestId("home-transplant");
  // the re-transplant, its month-only date never shown as a day, the count marked approximate
  expect(card).toHaveTextContent(/Бөөр · 2024\.03/);
  expect(card).toHaveTextContent(/Ойролцоогоор 2 жил 8 сар өнгөрсөн · ШУТИС/);
  expect(screen.getByRole(/button|link/, { name: "Бүх шилжүүлэн суулгалт (2)" })).toBeOnTheScreen();
});

test("Home: a failed graft says so; no transplant offers the wizard", async () => {
  transplants = [transplant({ graft_status: "failed" })];
  await openHome();
  expect(await screen.findByTestId("home-transplant")).toHaveTextContent(
    /Шилжүүлэн суулгасан эрхтэн: Ажиллахаа больсон/,
  );
});

test("Home without a transplant offers to add one", async () => {
  await openHome();
  expect(await screen.findByRole("button", { name: "Шилжүүлэн суулгалт нэмэх" })).toBeOnTheScreen();
});

test("Home: one tap records a dose through the same queue; the row stays for 'Буцаах'", async () => {
  await openHome();
  expect(await screen.findByText("Өнөөдөр 2 тунгаас 0 нь тэмдэглэгдсэн")).toBeOnTheScreen();
  const [taken] = await screen.findAllByRole("button", { name: /^Уусан — / });
  await fireEvent.press(taken);
  await waitFor(() => expect(posts.filter((p) => p.key === "intake")).toHaveLength(1));
  expect(posts[0].body).toMatchObject({ medication_id: MED_ID, status: "taken" });
  expect(await screen.findByText("✓ Уусан гэж тэмдэглэсэн")).toBeOnTheScreen();
  expect(await screen.findByRole(/button|link/, { name: /^Буцаах — / })).toBeOnTheScreen();
  expect(await screen.findByText("Өнөөдөр 2 тунгаас 1 нь тэмдэглэгдсэн")).toBeOnTheScreen();
  // Home never judges a dose (Q23)
  expect(screen.queryByText(/алдсан|мартсан|хоцорсон/)).toBeNull();
});

test("Home without medicines says so", async () => {
  medications = [];
  await openHome();
  expect(await screen.findByText("Өнөөдөр товлосон тун алга.")).toBeOnTheScreen();
});

test("Home: the next planned appointment - not a past, done or cancelled one", async () => {
  appointments = [
    appointment("a1", inDays(-1)),
    appointment("a2", inDays(9)),
    appointment("a3", inDays(2), { status: "cancelled" }),
    appointment("a4", inDays(3), { place: "Улсын II эмнэлэг" }),
    appointment("a5", inDays(1), { status: "done" }),
  ];
  await openHome();
  const card = await screen.findByTestId("home-appointment");
  expect(card).toHaveTextContent(/Үзлэг a4/);
  expect(card).toHaveTextContent(/Үзлэг · Улсын II эмнэлэг/);
});

test("Home without a coming appointment says so", async () => {
  appointments = [appointment("a1", inDays(-3))];
  await openHome();
  expect(await screen.findByText("Төлөвлөсөн товлол алга.")).toBeOnTheScreen();
});

test("Home: today's records not loaded - no count that could be wrong, doses still recordable", async () => {
  const intakes = handlers[`GET /api/v1/patients/${OWN.id}/intakes`];
  handlers[`GET /api/v1/patients/${OWN.id}/intakes`] = () =>
    json(500, { code: "internal", message_key: "error.internal" });
  try {
    await openHome();
    expect(await screen.findByText(/Өнөөдрийн тэмдэглэлийг ачаалж чадсангүй/)).toBeOnTheScreen();
    expect(screen.queryByText(/тунгаас .* нь тэмдэглэгдсэн/)).toBeNull();
    // the check before "Уусан" cannot answer either: the user is asked, then it is recorded
    const asked: string[] = [];
    jest.spyOn(Alert, "alert").mockImplementation((title, _message, buttons) => {
      asked.push(String(title));
      buttons?.find((b) => b.style !== "cancel")?.onPress?.();
    });
    const [taken] = screen.getAllByRole("button", { name: /^Уусан — / });
    await fireEvent.press(taken);
    await waitFor(() => expect(asked).toEqual([expect.stringMatching(/шалгаж чадсангүй/)]));
    await waitFor(() => expect(posts.filter((p) => p.key === "intake")).toHaveLength(1));
  } finally {
    jest.restoreAllMocks();
    handlers[`GET /api/v1/patients/${OWN.id}/intakes`] = intakes;
  }
});
