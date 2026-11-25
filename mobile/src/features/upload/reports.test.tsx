import { fireEvent, renderRouter, screen, waitFor } from "expo-router/testing-library";

import { clearAccessToken, setStatus } from "@/features/auth/session-store";
import { apiBaseUrl } from "@/lib/api-base";
import { queryClient } from "@/lib/query-client";

import { failReason, knownIssues } from "./use-reports";

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
  Paths: { document: "doc", cache: "cache" },
  Directory: class {
    exists = true;
    create() {}
    list() {
      return [];
    }
  },
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
const DOC = "22222222-2222-4222-8222-222222222222";
const document = (status: string, error_code: string | null = null) => ({
  id: DOC,
  mime_type: "application/pdf",
  size_bytes: 1000,
  page_count: 2,
  has_text_layer: true,
  status,
  error_code,
  created_at: "2026-11-12T03:00:00Z",
});
const result = (position: number, extra: Record<string, unknown>) => ({
  id: `33333333-3333-4333-8333-33333333333${position}`,
  position,
  test_code: null,
  test_name_mn: null,
  test_name_en: null,
  raw_unit: null,
  value_numeric: null,
  comparator: null,
  value_text: null,
  qualitative: null,
  ref_text: null,
  ref_low: null,
  ref_high: null,
  critical_text: null,
  critical_low: null,
  critical_high: null,
  lab_flag: null,
  flag: "unknown",
  flag_source: null,
  flag_mismatch: false,
  unit_canonical: null,
  value_canonical: null,
  issues: [] as string[],
  acknowledged: [] as string[],
  edited_by_user: false,
  read_value: null,
  read_critical_text: null,
  source_page: 1,
  ...extra,
});
const REPORT = {
  id: "44444444-4444-4444-8444-444444444444",
  document_id: DOC,
  method: "local",
  status: "needs_review",
  lab_name: "Улсын Нэгдүгээр Төв Эмнэлэг",
  panel_name: "Биохими",
  specimen: "Ийлдэс",
  collected_at: "2025-05-02T16:00:00Z",
  collected_precision: "day",
  collected_by_user: false,
  analysed_at: null,
  reported_at: null,
  date_ambiguous: false,
  name_match_score: "1.00",
  has_unconfirmed_critical: false,
  source: "read",
  created_at: "2026-11-12T03:00:05Z",
  last_doses: [] as unknown[],
  results: [
    result(0, {
      test_code: "CREA",
      test_name_mn: "Креатинин",
      raw_name: "Креатинин",
      raw_value: "88",
      raw_unit: "мкмоль/л",
      value_numeric: "88",
      ref_text: "62 - 115",
      lab_flag: "H",
      flag: "normal",
      flag_source: "computed_document_range",
    }),
    result(1, {
      raw_name: "Зохиомол маркер",
      raw_value: "1,2",
      raw_unit: "ед",
      issues: ["unknown_test"],
    }),
  ],
};

let documents: ReturnType<typeof document>[] = [];
let reports: (typeof REPORT)[] = [];

const handlers: Record<string, () => Response> = {
  "POST /api/v1/auth/refresh": () =>
    json(200, { access_token: "a1", token_type: "bearer", expires_in: 900, refresh_token: "r1" }),
  "GET /api/v1/me": () => json(200, { locale: "mn", display_name: "Бат" }),
  "GET /api/v1/me/consents": () => json(200, consents),
  "GET /api/v1/me/notifications": () => json(200, []),
  "GET /api/v1/healthz": () => json(200, { status: "ok" }),
  "GET /api/v1/patients": () => json(200, [OWN]),
  [`GET /api/v1/patients/${OWN.id}/transplants`]: () =>
    json(200, [
      {
        id: "t1",
        client_id: "55555555-5555-4555-8555-555555555555",
        organ: "kidney",
        transplant_date: "2021-06-14",
        date_precision: "day",
        country: "MN",
        hospital: "Эмнэлэг",
        transplant_number: 1,
        elapsed: { days: 2000, months: 66, years: 5, approximate: false },
        created_at: "2026-11-04T00:00:00Z",
        updated_at: null,
      },
    ]),
  [`GET /api/v1/patients/${OWN.id}/documents`]: () => json(200, documents),
  [`GET /api/v1/patients/${OWN.id}/documents/${DOC}/reports`]: () => json(200, reports),
};
let sent: { method: string; path: string; body: unknown }[] = [];

/** What the server would answer: an accepted issue is kept, a confirm confirms. */
function answer(path: string, body: { acknowledge?: string[] } | null) {
  const [report] = reports;
  if (path.endsWith("/confirm")) {
    reports = [{ ...report, status: "confirmed" }];
    return reports[0];
  }
  const rowId = path.match(/results\/([0-9a-f-]+)$/)?.[1];
  const next = {
    ...report,
    results: report.results.map((r) =>
      r.id === rowId && body?.acknowledge
        ? { ...r, acknowledged: [...r.acknowledged, ...body.acknowledge] }
        : r,
    ),
  };
  reports = [next];
  return next;
}

async function openResults() {
  await renderRouter("./src/app", { initialUrl: "/" });
  await fireEvent.press(await screen.findByRole("button", { name: /Шинжилгээний хариу\./ }));
}

beforeEach(() => {
  queryClient.clear();
  clearAccessToken();
  setStatus("loading");
  mockStore.clear();
  mockStore.set("lt.refresh", "r0");
  documents = [];
  reports = [];
  sent = [];
  globalThis.fetch = jest.fn(async (input: Request | string, init?: RequestInit) => {
    const request = typeof input === "string" ? new Request(input, init) : input;
    const path = request.url.slice(apiBaseUrl.length);
    const handler = handlers[`${request.method} ${path}`];
    if (handler) return handler();
    // review writes: answered with the report as the server would have it (5.5)
    if (path.startsWith(`/api/v1/patients/${OWN.id}/reports/`)) {
      const body = request.method === "GET" ? null : await request.clone().text();
      sent.push({ method: request.method, path, body: body ? JSON.parse(body) : null });
      return json(200, answer(path, body ? JSON.parse(body) : null));
    }
    return json(404, { code: "not_found", message_key: "error.not_found" });
  }) as unknown as typeof fetch;
});

test("a read document opens its draft: rows as printed, the flag, what to check", async () => {
  documents = [document("needs_review")];
  reports = [REPORT];
  await openResults();
  await fireEvent.press(await screen.findByTestId(`document-${DOC}`));
  expect(await screen.findByText("Биохими")).toBeOnTheScreen();
  expect(screen.getByText(/автоматаар уншсан ноорог/)).toBeOnTheScreen();
  expect(screen.getByText("Огноо: 2025.05.03")).toBeOnTheScreen(); // a day, no time
  expect(screen.getByText("Ноорог — батлаагүй")).toBeOnTheScreen();
  expect(screen.getByText("88 мкмоль/л")).toBeOnTheScreen();
  expect(screen.getByText("Лавлах хэмжээ: 62 - 115")).toBeOnTheScreen();
  expect(screen.getByText("! шинжилгээ танигдсангүй")).toBeOnTheScreen();
  // the flag the server computed from the printed range, never the lab's own mark
  expect(screen.getByText(/Лавлах хэмжээнд/)).toBeOnTheScreen();
  expect(screen.queryByText("H")).toBeNull();
  expect(screen.queryByText(/AI-аар/)).toBeNull();
  expect(screen.queryByTestId("critical-banner")).toBeNull();
});

test("confirm waits until every issue is looked at, one at a time", async () => {
  documents = [document("needs_review")];
  reports = [REPORT];
  await openResults();
  await fireEvent.press(await screen.findByTestId(`document-${DOC}`));
  expect(await screen.findByText("1 мөр шалгах шаардлагатай")).toBeOnTheScreen();
  const confirm = screen.getByRole("button", { name: /^Батлах\./ });
  expect(confirm).toBeDisabled();
  await fireEvent.press(
    screen.getByRole("button", { name: /«шинжилгээ танигдсангүй»: хариутай ижил/ }),
  );
  expect(await screen.findByText("Бүх мөр шалгагдсан")).toBeOnTheScreen();
  expect(sent[0]).toMatchObject({
    method: "PATCH",
    body: { acknowledge: ["unknown_test"] },
  });
  await fireEvent.press(screen.getByRole("button", { name: /^Батлах\./ }));
  expect(await screen.findByText(/Батлагдсан/)).toBeOnTheScreen();
  expect(sent.at(-1)?.path).toMatch(/\/confirm$/);
});

test("an implausible value is kept only when typed again from the report (Q57)", async () => {
  documents = [document("needs_review")];
  reports = [
    {
      ...REPORT,
      results: [REPORT.results[0], { ...REPORT.results[1], issues: ["implausible"] }],
    },
  ];
  await openResults();
  await fireEvent.press(await screen.findByTestId(`document-${DOC}`));
  await fireEvent.press(
    await screen.findByRole("button", { name: /«уншилтын алдаа байж магадгүй»: хариутай ижил/ }),
  );
  expect(sent.filter((x) => x.method === "PATCH")).toHaveLength(0); // a tap is not enough
  const done = screen.getByRole("button", { name: "Хариутай тулгасан" });
  expect(done).toBeDisabled();
  await fireEvent.changeText(screen.getByTestId("retype-1"), "1,2");
  await fireEvent.press(done);
  await waitFor(() =>
    expect(sent.find((x) => x.method === "PATCH")).toMatchObject({
      body: { acknowledge: ["implausible"], retyped_value: "1,2" },
    }),
  );
});

test("a drug level without the sample time may get one, on the printed date (Q54)", async () => {
  documents = [document("needs_review")];
  reports = [
    {
      ...REPORT,
      last_doses: [
        {
          test_code: "CREA",
          medication_id: "m1",
          medication_name: "Такролимус",
          taken_at: null,
          minutes_before: null,
          time_unknown: true,
          other_records: 0,
        },
      ],
    },
  ];
  await openResults();
  await fireEvent.press(await screen.findByTestId(`document-${DOC}`));
  expect(await screen.findByText(/дээж авсан цаг бичигдээгүй/)).toBeOnTheScreen();
  await fireEvent.press(screen.getByRole("button", { name: "Дээж авсан цагийг нэмэх" }));
  expect(screen.getByRole("button", { name: "Цагийг хадгалах" })).toBeDisabled();
  expect(screen.getByText(/Дээж авсан цаг/)).toBeOnTheScreen();
});

test("Q65: a date or time the person entered says so, never shown as the lab's", async () => {
  documents = [document("needs_review")];
  reports = [{ ...REPORT, collected_by_user: true }];
  await openResults();
  await fireEvent.press(await screen.findByTestId(`document-${DOC}`));
  expect(
    await screen.findByText(/Огноо, цагийг хэрэглэгч оруулсан эсвэл зассан \(апп уншаагүй\)/),
  ).toBeOnTheScreen();
});

test("Q65: the time since the last dose says the sample time is the person's", async () => {
  documents = [document("needs_review")];
  reports = [
    {
      ...REPORT,
      collected_by_user: true,
      last_doses: [
        {
          test_code: "CREA",
          medication_id: "m1",
          medication_name: "Такролимус",
          taken_at: "2025-05-02T12:00:00Z",
          minutes_before: 720,
          time_unknown: false,
          other_records: 0,
        },
      ],
    },
  ];
  await openResults();
  await fireEvent.press(await screen.findByTestId(`document-${DOC}`));
  expect(
    await screen.findByText(/Такролимус.*12 цаг.*· ✎ Огноо, цагийг гараар оруулсан\/зассан/),
  ).toBeOnTheScreen();
});

test("a draft that may be critical opens under a red banner, its row first", async () => {
  documents = [document("needs_review")];
  reports = [
    {
      ...REPORT,
      has_unconfirmed_critical: true,
      results: [
        REPORT.results[1],
        result(2, {
          raw_name: "Кали",
          raw_value: "6,9",
          raw_unit: "ммоль/л",
          critical_text: "> 6.5",
          flag: "critical_high",
        }),
      ],
    },
  ];
  await openResults();
  await fireEvent.press(await screen.findByTestId(`document-${DOC}`));
  expect(await screen.findByTestId("critical-banner")).toBeOnTheScreen();
  expect(screen.getByText(/103 руу залгана уу/)).toBeOnTheScreen();
  expect(screen.getByText(/Критик хязгаараас их/)).toBeOnTheScreen();
  const rows = screen.getAllByTestId(/^result-/).map((r) => r.props.testID);
  expect(rows[0]).toBe("result-2"); // the critical row comes first
});

test("an ambiguous date is picked, never accepted", async () => {
  documents = [document("needs_review")];
  reports = [
    {
      ...REPORT,
      results: REPORT.results.map((r) => ({ ...r, issues: [...r.issues, "date_ambiguous"] })),
    },
  ];
  await openResults();
  await fireEvent.press(await screen.findByTestId(`document-${DOC}`));
  expect(await screen.findByTestId("date-editor")).toBeOnTheScreen();
  // no "matches the printout" for the date
  expect(screen.queryByRole("button", { name: /«огноо тодорхойгүй»/ })).toBeNull();
  expect(screen.getByRole("button", { name: "Огноог хадгалах" })).toBeDisabled();
});

test("a document not read automatically says so, and does not open", async () => {
  documents = [document("failed", "ai_unconfigured")];
  await openResults();
  expect(await screen.findByText(/Автоматаар уншиж чадсангүй/)).toBeOnTheScreen();
  expect(screen.queryByText("Уншсан утгуудыг харах")).toBeNull();
});

test("an AI reading carries its warning", async () => {
  documents = [document("needs_review")];
  reports = [{ ...REPORT, method: "ai" }];
  await openResults();
  await fireEvent.press(await screen.findByTestId(`document-${DOC}`));
  expect(await screen.findByText(/AI-аар уншсан/)).toBeOnTheScreen();
});

test("fail reasons and issue codes", () => {
  expect(failReason(null)).toBe("temporary");
  expect(failReason("infected")).toBe("infected");
  expect(failReason("extraction_timeout")).toBe("temporary");
  expect(failReason("not_read")).toBe("not_read");
  expect(failReason("ai_refused")).toBe("not_read");
  // a code the app does not know yet is never dropped
  expect(knownIssues(["unknown_test", "something_new", "later"])).toEqual([
    "unknown_test",
    "other",
  ]);
  expect(knownIssues(["name_missing", "truncated"])).toEqual(["name_missing", "truncated"]);
});

test("editing a row sends only what changed; the server computes the rest", async () => {
  documents = [document("needs_review")];
  reports = [REPORT];
  handlers[`GET /api/v1/lab-tests`] = () =>
    json(200, [
      {
        code: "CREA",
        name_mn: "Креатинин",
        name_en: "Creatinine",
        canonical_unit: "µmol/L",
        category: "renal",
      },
    ]); // prettier-ignore
  await openResults();
  await fireEvent.press(await screen.findByTestId(`document-${DOC}`));
  const editButtons = await screen.findAllByRole("button", { name: "Засах" });
  await fireEvent.press(editButtons[0]);
  const value = await screen.findByTestId("row-value");
  await fireEvent.changeText(value, "1,3");
  await fireEvent.press(screen.getByRole("button", { name: "Хадгалах" }));
  expect(await screen.findByTestId("document-reports")).toBeOnTheScreen();
  const patch = sent.find((x) => x.method === "PATCH");
  expect(patch?.body).toEqual({ raw_value: "1,3" });
});
