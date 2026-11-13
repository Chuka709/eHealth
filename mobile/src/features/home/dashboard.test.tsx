import { fireEvent, renderRouter, screen, waitFor } from "expo-router/testing-library";
import { Alert, type AlertButton } from "react-native";

import { clearAccessToken, setStatus } from "@/features/auth/session-store";
import { apiBaseUrl } from "@/lib/api-base";
import { queryClient } from "@/lib/query-client";

import { percentText } from "./use-dashboard";

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
const consents = ["terms", "privacy", "sensitive_data"].map((kind) => ({
  kind,
  current_version: "draft-2026-10",
  granted: true,
  granted_version: "draft-2026-10",
  at: "2026-10-01T00:00:00Z",
  required: true,
}));
const P = `/api/v1/patients/${OWN.id}`;

const value = (over: Record<string, unknown>) => ({
  result_id: "r1",
  report_id: "rep1",
  collected_at: "2026-10-14T00:30:00Z",
  raw_value: "1,20",
  raw_unit: "мг/дл",
  comparator: null,
  value_text: null,
  qualitative: null,
  value: "106",
  unit: "µmol/L",
  ref_text: "0.6-1.1",
  ref_low: "53",
  ref_high: "97",
  flag: "high",
  possibly_critical: false,
  ...over,
});
let dashboard: Record<string, unknown> = {};
let puts: unknown[] = [];
let deletes = 0;
const handlers: Record<string, (r: Request) => Response | Promise<Response>> = {
  "POST /api/v1/auth/refresh": () =>
    json(200, { access_token: "a1", token_type: "bearer", expires_in: 900, refresh_token: "r1" }),
  "GET /api/v1/me": () => json(200, { locale: "mn", display_name: "Бат" }),
  "GET /api/v1/me/consents": () => json(200, consents),
  "GET /api/v1/me/notifications": () => json(200, []),
  "GET /api/v1/healthz": () => json(200, { status: "ok" }),
  "GET /api/v1/patients": () => json(200, [OWN]),
  [`GET ${P}/transplants`]: () => json(200, []),
  [`GET ${P}/medications`]: () => json(200, []),
  [`GET ${P}/appointments`]: () => json(200, []),
  [`GET ${P}/timezone`]: () =>
    json(200, { home: "Asia/Ulaanbaatar", current: "Asia/Ulaanbaatar", switches: [] }),
  [`GET ${P}/trends`]: () =>
    json(200, [
      {
        test_code: "TAC",
        name_mn: "Такролимус",
        name_en: "Tacrolimus",
        category: "immunosuppressant",
        results: 2,
        latest: "2026-06-01T00:30:00Z",
      },
      {
        test_code: "CREA",
        name_mn: "Креатинин",
        name_en: "Creatinine",
        category: "renal",
        results: 1,
        latest: "2026-04-01T00:30:00Z",
      },
    ]),
  [`GET ${P}/trends/CREA`]: () =>
    json(200, {
      test: {
        code: "CREA",
        name_mn: "Креатинин",
        name_en: "Creatinine",
        unit: "µmol/L",
        decimals: 0,
        kind: "numeric",
        category: "renal",
      },
      points: [],
      truncated: false,
      doses: [],
      transplants: [],
      events: [],
      axis: null,
    }),
  [`GET ${P}/dashboard`]: () => json(200, dashboard),
  [`PUT ${P}/dashboard/cards`]: async (r) => {
    puts.push(await r.json());
    return new Response(null, { status: 204 });
  },
  [`DELETE ${P}/dashboard/cards`]: () => {
    deletes += 1;
    return new Response(null, { status: 204 });
  },
};

beforeEach(() => {
  queryClient.clear();
  clearAccessToken();
  setStatus("loading");
  mockStore.clear();
  mockStore.set("lt.refresh", "r0");
  mockStore.set("lt.account", "00000000-0000-4000-8000-000000000001");
  puts = [];
  deletes = 0;
  dashboard = {
    custom: false,
    attention: [
      {
        test_code: "K",
        name_mn: "Кали",
        name_en: "Potassium",
        latest: value({
          raw_value: "6.9",
          raw_unit: "ммоль/л",
          flag: "unknown",
          possibly_critical: true,
          ref_text: null,
        }),
      },
    ],
    cards: [
      {
        test_code: "CREA",
        name_mn: "Креатинин",
        name_en: "Creatinine",
        latest: value({}),
        change: {
          percent: "20",
          previous_value: "88",
          previous_collected_at: "2026-09-14T00:30:00Z",
          previous_raw_value: "1,00",
          previous_raw_unit: "мг/дл",
        },
        spark: [
          { collected_at: "2026-09-14T00:30:00Z", value: "88", comparator: null },
          { collected_at: "2026-10-14T00:30:00Z", value: "106", comparator: null },
        ],
        spark_unit: "µmol/L",
      },
      {
        test_code: "HGB",
        name_mn: "Гемоглобин",
        name_en: "Haemoglobin",
        latest: null,
        change: null,
        spark: [],
        spark_unit: null,
      },
    ],
  };
  globalThis.fetch = jest.fn(async (input: Request | string, init?: RequestInit) => {
    const request = typeof input === "string" ? new Request(input, init) : input;
    const path = request.url.slice(apiBaseUrl.length).split("?")[0];
    const handler = handlers[`${request.method} ${path}`];
    return handler
      ? handler(request)
      : json(404, { code: "not_found", message_key: "error.not_found" });
  }) as unknown as typeof fetch;
});
afterEach(() => queryClient.clear());

test("the sign of the change is the server's number with a sign, nothing more", () => {
  expect([percentText("20"), percentText("-25"), percentText("0")]).toEqual(["+20%", "−25%", "0%"]);
});

test("Home lists what to look at and the key cards as printed, and opens a trend", async () => {
  await renderRouter("./src/app", { initialUrl: "/" });
  expect(await screen.findByTestId("home-attention")).toBeOnTheScreen();
  // never called critical: the lab marked it, or its limit could not be read
  expect(screen.getByText(/эх хариугаа шалгана уу/)).toBeOnTheScreen();
  expect(screen.getByText("1,20 мг/дл")).toBeOnTheScreen();
  expect(screen.getByText("Өмнөхөөс өөрчлөлт: +20% (2026.09.14: 1,00 мг/дл)")).toBeOnTheScreen();
  expect(screen.getByText("Лавлах: 0.6-1.1 · 2026.10.14")).toBeOnTheScreen();
  expect(screen.getByText("Батлагдсан хариу алга")).toBeOnTheScreen();
  await fireEvent.press(screen.getByTestId("card-CREA"));
  await waitFor(() => expect(screen.getByTestId("trend-screen")).toBeOnTheScreen());
});

test("the cards are reordered and saved as one list, or set back to the organ's", async () => {
  // the reset asks first; this test confirms it
  const alert = jest.spyOn(Alert, "alert").mockImplementation((_t, _m, buttons?: AlertButton[]) => {
    buttons?.find((b) => b.style === "destructive")?.onPress?.();
  });
  await renderRouter("./src/app", { initialUrl: "/" });
  await fireEvent.press(await screen.findByRole(/button|link/, { name: "Картуудыг засах" }));
  expect(await screen.findByTestId("edit-CREA")).toBeOnTheScreen();
  await fireEvent.press(screen.getByRole("button", { name: "Гемоглобин-г дээш" }));
  await fireEvent.press(screen.getByRole("button", { name: "Хадгалах" }));
  await waitFor(() => expect(puts).toEqual([{ test_codes: ["HGB", "CREA"] }]));
  await fireEvent.press(await screen.findByRole(/button|link/, { name: "Картуудыг засах" }));
  await fireEvent.press(
    await screen.findByRole(/button|link/, { name: "Эрхтний анхдагч картууд руу буцаах" }),
  );
  await waitFor(() => expect(deletes).toBe(1));
  expect(alert).toHaveBeenCalledTimes(1);
});
