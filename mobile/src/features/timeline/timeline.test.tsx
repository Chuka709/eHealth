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

const item = (over: Record<string, unknown>) => ({
  kind: "report",
  id: "rep-1",
  day: "2026-10-14",
  precision: "minute",
  at: "2026-10-14T00:30:00Z",
  title: "УНТЭ",
  detail: "read",
  ref_id: "doc-1",
  until: null,
  results: 4,
  flagged: 1,
  unflagged: 2,
  planned: false,
  ...over,
});
const report = (id: string, at: string, lab: string, value: string, ref: string) => ({
  id,
  document_id: null,
  extraction_run_id: null,
  method: null,
  source: "typed",
  status: "confirmed",
  lab_name: lab,
  specimen: null,
  collected_at: at,
  collected_precision: "minute",
  date_ambiguous: false,
  name_match_score: null,
  has_unconfirmed_critical: false,
  created_at: at,
  acknowledged: [],
  last_doses: [],
  results: [
    {
      id: `${id}-r`,
      position: 0,
      test_code: "CREA",
      test_name_mn: "Креатинин",
      test_name_en: "Creatinine",
      raw_name: "Креатинин",
      raw_value: value,
      raw_unit: "мкмоль/л",
      value_numeric: value,
      comparator: null,
      value_text: null,
      qualitative: null,
      ref_text: ref,
      ref_low: null,
      ref_high: null,
      critical_text: null,
      critical_low: null,
      critical_high: null,
      lab_flag: null,
      unit_canonical: "µmol/L",
      value_canonical: value,
      ref_low_canonical: null,
      ref_high_canonical: null,
      critical_low_canonical: null,
      critical_high_canonical: null,
      flag: "normal",
      flag_source: "computed_document_range",
      flag_mismatch: false,
      confidence: null,
      issues: [],
      acknowledged: [],
      source_page: null,
      read_value: null,
    },
  ],
});
let timelineQueries: string[] = [];
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
  [`GET ${P}/timeline/labs`]: () => json(200, []),
  [`GET ${P}/timeline`]: (r) => {
    timelineQueries.push(new URL(r.url).search);
    return json(200, {
      next: null,
      items: [
        item({
          kind: "medication_stopped",
          id: "m1",
          day: "2026-12-01",
          precision: "day",
          at: null,
          title: "Програф",
          detail: null,
          ref_id: null,
          results: null,
          flagged: null,
          unflagged: null,
          planned: true,
        }),
        item({}),
        item({
          id: "rep-2",
          day: "2026-09-14",
          at: "2026-09-14T00:30:00Z",
          title: "Хувийн лаб",
          flagged: 0,
          unflagged: 0,
        }),
        item({
          kind: "transplant",
          id: "t1",
          day: "2021-01-01",
          precision: "year",
          at: null,
          title: "kidney",
          detail: "functioning",
          ref_id: null,
          results: null,
          flagged: null,
          unflagged: null,
        }),
      ],
    });
  },
  [`GET ${P}/reports/rep-1`]: () =>
    json(200, report("rep-1", "2026-10-14T00:30:00Z", "УНТЭ", "128", "62-106")),
  [`GET ${P}/reports/rep-2`]: () =>
    json(200, report("rep-2", "2026-09-14T00:30:00Z", "Хувийн лаб", "98", "53-115")),
};

beforeEach(() => {
  queryClient.clear();
  clearAccessToken();
  setStatus("loading");
  mockStore.clear();
  mockStore.set("lt.refresh", "r0");
  mockStore.set("lt.account", "00000000-0000-4000-8000-000000000001");
  timelineQueries = [];
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

async function openTimeline() {
  await renderRouter("./src/app", { initialUrl: "/" });
  await fireEvent.press(await screen.findByTestId("home-timeline"));
}

test("the timeline says each entry as recorded: planned, the stop day, counts, a year-only date", async () => {
  await openTimeline();
  expect(await screen.findByText("Програф — энэ өдрөөс эхлэн уухгүй")).toBeOnTheScreen();
  expect(screen.getByText(/^Төлөвлөсөн · /)).toBeOnTheScreen();
  // counts, never "all fine"
  expect(screen.getByText("Хязгаараас гадуур гэж тэмдэглэгдсэн: 1 / 4")).toBeOnTheScreen();
  expect(screen.getByText("Лавлахтай тулгаагүй: 2")).toBeOnTheScreen();
  // a transplant known only to the year sits under its year, not January
  expect(screen.getByText("2021 он")).toBeOnTheScreen();
  expect(screen.getByText("2021 он (сар, өдөр тодорхойгүй)")).toBeOnTheScreen();
  expect(screen.queryByText("2021 оны 1-р сар")).toBeNull();
});

test("two reports are compared side by side, each as printed, the older first", async () => {
  await openTimeline();
  await fireEvent.press(await screen.findByRole(/button|link/, { name: "Хоёр хариу харьцуулах" }));
  await fireEvent.press(screen.getByTestId("tl-report-rep-1"));
  await fireEvent.press(screen.getByTestId("tl-report-rep-2"));
  await fireEvent.press(screen.getByRole(/button|link/, { name: "Харьцуулах (2/2)" }));
  expect(await screen.findByTestId("compare-screen")).toBeOnTheScreen();
  const values = screen.getAllByText(/мкмоль\/л$/).map((n) => n.props.children);
  expect(values).toEqual(["98 мкмоль/л", "128 мкмоль/л"]);
  expect(screen.getByText("Лавлах хэмжээ: 53-115")).toBeOnTheScreen();
  expect(screen.getByText("Лавлах хэмжээ: 62-106")).toBeOnTheScreen();
});

test("a filter asks the server for those kinds only", async () => {
  await openTimeline();
  await screen.findByText("Програф — энэ өдрөөс эхлэн уухгүй");
  await fireEvent.press(screen.getByRole("checkbox", { name: "Эм" }));
  await waitFor(() => expect(timelineQueries.at(-1)).not.toMatch(/medication/));
});

test("a test printed twice in one report is compared twice, with its printed names", async () => {
  const twice = report("rep-1", "2026-10-14T00:30:00Z", "УНТЭ", "128", "62-106");
  twice.results.push({
    ...twice.results[0],
    id: "rep-1-u",
    position: 1,
    raw_name: "Креатинин (шээс)",
    raw_value: "9800",
    ref_text: "5300-17700",
  });
  const keep = handlers[`GET ${P}/reports/rep-1`];
  handlers[`GET ${P}/reports/rep-1`] = () => json(200, twice);
  try {
    await openTimeline();
    await fireEvent.press(
      await screen.findByRole(/button|link/, { name: "Хоёр хариу харьцуулах" }),
    );
    await fireEvent.press(screen.getByTestId("tl-report-rep-1"));
    await fireEvent.press(screen.getByTestId("tl-report-rep-2"));
    await fireEvent.press(screen.getByRole(/button|link/, { name: "Харьцуулах (2/2)" }));
    expect(await screen.findByTestId("cmp-CREA#2")).toBeOnTheScreen();
    expect(screen.getByText("9800 мкмоль/л")).toBeOnTheScreen();
    expect(screen.getByText("Креатинин (шээс)")).toBeOnTheScreen();
  } finally {
    handlers[`GET ${P}/reports/rep-1`] = keep;
  }
});
