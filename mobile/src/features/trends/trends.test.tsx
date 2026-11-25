import { colors } from "@labtrack/shared";
import { fireEvent, renderRouter, screen, waitFor } from "expo-router/testing-library";

import { clearAccessToken, setStatus } from "@/features/auth/session-store";
import { apiBaseUrl } from "@/lib/api-base";
import { queryClient } from "@/lib/query-client";

import { trendOption } from "./chart-option";
import type { Trend } from "./use-trends";

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

const point = (over: Partial<Trend["points"][number]>): Trend["points"][number] => ({
  result_id: "r1",
  report_id: "rep1",
  document_id: "doc1",
  lab_name: "УНТЭ",
  raw_name: "Такролимус",
  collected_at: "2026-05-01T00:30:00Z",
  collected_precision: "minute",
  collected_by_user: false,
  days_since_transplant: 300,
  around_transplant: false,
  raw_value: "7,2",
  raw_unit: "нг/мл",
  comparator: null,
  value_text: null,
  qualitative: null,
  value: "7.2",
  unit: "ng/mL",
  ref_text: "5-10",
  ref_low: "5",
  ref_high: "10",
  critical_text: null,
  critical_low: null,
  critical_high: null,
  flag: "normal",
  possibly_critical: false,
  ...over,
});
const TREND: Trend = {
  test: {
    code: "TAC",
    name_mn: "Такролимус",
    name_en: "Tacrolimus",
    unit: "ng/mL",
    decimals: 1,
    kind: "numeric",
    category: "immunosuppressant",
  },
  points: [
    point({}),
    point({
      result_id: "r2",
      collected_at: "2026-06-01T00:30:00Z",
      raw_value: "12.4",
      value: "12.4",
      ref_low: "4",
      ref_high: "12",
      ref_text: "4-12",
      lab_name: "Другой",
      raw_name: "Tacrolimus (CMIA)",
      flag: "high",
    }),
  ],
  truncated: false,
  doses: [
    {
      medication_id: "m1",
      name: "Програф",
      series: [
        {
          unit: "mg",
          unit_text: null,
          steps: [
            {
              starts_on: "2026-01-01",
              ends_before: "2026-05-15",
              amount: "4",
              schedule_type: "daily",
              days: [],
              planned: false,
            },
            {
              starts_on: "2026-05-15",
              ends_before: null,
              amount: "3.5",
              schedule_type: "daily",
              days: [],
              planned: false,
            },
          ],
        },
      ],
    },
  ],
  transplants: [
    {
      id: "t1",
      organ: "kidney",
      transplant_date: "2025-07-05",
      date_precision: "day",
      graft_status: "functioning",
    },
  ],
  events: [],
  axis: { transplant_id: "t1", day_zero: "2025-07-05", approximate: false },
}; // fmt-friendly fixture

let trendQueries: string[] = [];
const handlers: Record<string, (r: Request) => Response> = {
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
  [`GET ${P}/trends/TAC`]: (r) => {
    trendQueries.push(new URL(r.url).search);
    return json(200, TREND);
  },
};

beforeEach(() => {
  queryClient.clear();
  clearAccessToken();
  setStatus("loading");
  mockStore.clear();
  mockStore.set("lt.refresh", "r0");
  mockStore.set("lt.account", "00000000-0000-4000-8000-000000000001");
  trendQueries = [];
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

const labels = {
  value: "v",
  refLow: "rl",
  refHigh: "rh",
  criticalLow: "cl",
  criticalHigh: "ch",
  dose: "d",
  days: "days",
};

test("the option draws each point's own range, flags as symbols, and the doses as steps", () => {
  const option = trendOption(TREND, colors.light, {
    axis: "date",
    today: "2026-07-01",
    labels,
    unitLabel: (u: string) => `[${u}]`,
  }) as {
    series: {
      name: string;
      data: unknown[];
      yAxisIndex?: number;
      markLine?: { data: unknown[] };
    }[];
  };
  const byName = Object.fromEntries(option.series.map((s) => [s.name, s]));
  // a change of lab is a step of the range (rule 5), not one range for all
  expect(byName.rh.data).toEqual([
    ["2026-05-01T00:30:00Z", 10],
    ["2026-06-01T00:30:00Z", 12],
  ]);
  expect(byName.cl).toBeUndefined(); // no critical limit printed: none drawn
  const values = byName.v.data as { symbol: string }[];
  expect(values.map((d) => d.symbol)).toEqual(["circle", "triangle"]);
  expect(byName.v.markLine?.data).toEqual([{ xAxis: "2025-07-05" }]);
  expect(byName.d.yAxisIndex).toBe(1);
  expect(byName.d.data).toEqual([
    ["2026-01-01", 4],
    ["2026-05-15", 4],
    ["2026-05-15", null],
    ["2026-05-15", 3.5],
    ["2026-07-01", 3.5],
  ]);
});

test("on the days axis the points sit at their days since transplant, without doses", () => {
  const option = trendOption(TREND, colors.light, {
    axis: "days",
    today: "2026-07-01",
    labels,
    unitLabel: (u: string) => u,
  }) as {
    series: { name: string; data: unknown[] }[];
  };
  expect(option.series.map((s) => s.name)).not.toContain("d");
  const values = option.series.find((s) => s.name === "v")?.data as { value: unknown[] }[];
  expect(values[0].value).toEqual([300, 7.2]);
});

test("the Trends tab lists tested tests and opens a chart with every value as text", async () => {
  await renderRouter("./src/app", { initialUrl: "/" });
  await fireEvent.press(await screen.findByRole("button", { name: /^Хандлага/ }));
  expect(await screen.findByTestId("trend-CREA")).toBeOnTheScreen();
  await fireEvent.changeText(screen.getByLabelText("Шинжилгээ хайх"), "такро");
  expect(screen.queryByTestId("trend-CREA")).toBeNull();
  await fireEvent.press(screen.getByTestId("trend-TAC"));
  expect(await screen.findByTestId("trend-chart")).toBeOnTheScreen();
  // as printed, with the result's own range and flag in text
  expect(screen.getByText("12.4 нг/мл")).toBeOnTheScreen();
  expect(screen.getByText("↑ Лавлахаас их")).toBeOnTheScreen();
  expect(screen.getByText("Лавлах хэмжээ: 4-12")).toBeOnTheScreen();
  // the printed name only where it says more than the catalog name (Q70)
  expect(screen.getByText("Хариун дээрх нэр: Tacrolimus (CMIA)")).toBeOnTheScreen();
  expect(screen.queryByText("Хариун дээрх нэр: Такролимус")).toBeNull();
  expect(screen.getByText(/Тун ба шинжилгээний хариуны холбоог эмч тайлбарлана/)).toBeOnTheScreen();
  expect(trendQueries[0]).toMatch(/since=/); // 1 year by default
  await fireEvent.press(screen.getByRole("radio", { name: "Бүгд" }));
  await waitFor(() => expect(trendQueries.at(-1)).toBe(""));
});

test("a '< x' value is hollow whatever its flag, and planned or weekly doses are not drawn", () => {
  const trend: Trend = {
    ...TREND,
    points: [point({ comparator: "<", raw_value: "<2", value: "2", flag: "critical_low" })],
    doses: [
      {
        medication_id: "m1",
        name: "Програф",
        series: [
          {
            unit: "mg",
            unit_text: null,
            steps: [
              {
                starts_on: "2026-01-01",
                ends_before: "2026-03-01",
                amount: "4",
                schedule_type: "weekly",
                days: [1, 4],
                planned: false,
              },
              {
                starts_on: "2026-03-01",
                ends_before: "2026-08-01",
                amount: "3",
                schedule_type: "daily",
                days: [],
                planned: false,
              },
              {
                starts_on: "2026-08-01",
                ends_before: null,
                amount: "2",
                schedule_type: "daily",
                days: [],
                planned: true,
              },
            ],
          },
        ],
      },
    ],
  };
  const option = trendOption(trend, colors.light, {
    axis: "date",
    today: "2026-07-01",
    labels,
    unitLabel: (u: string) => u,
  }) as { series: { name: string; data: unknown[] }[] };
  const byName = Object.fromEntries(option.series.map((s) => [s.name, s]));
  expect((byName.v.data as { symbol: string }[])[0].symbol).toBe("emptyTriangle");
  // the weekly step is a gap; the daily one stops today; the planned one is not drawn
  expect(byName.d.data).toEqual([
    ["2026-01-01", null],
    ["2026-03-01", 3],
    ["2026-07-01", 3],
  ]);
});
