import { fireEvent, renderRouter, screen } from "expo-router/testing-library";

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
  issues: [],
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
  analysed_at: null,
  reported_at: null,
  date_ambiguous: false,
  name_match_score: "1.00",
  has_unconfirmed_critical: false,
  created_at: "2026-11-12T03:00:05Z",
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
  globalThis.fetch = jest.fn(async (input: Request | string, init?: RequestInit) => {
    const request = typeof input === "string" ? new Request(input, init) : input;
    const handler = handlers[`${request.method} ${request.url.slice(apiBaseUrl.length)}`];
    return handler ? handler() : json(404, { code: "not_found", message_key: "error.not_found" });
  }) as unknown as typeof fetch;
});

test("a read document opens its draft: rows as printed, what to check, no flags", async () => {
  documents = [document("needs_review")];
  reports = [REPORT];
  await openResults();
  await fireEvent.press(await screen.findByTestId(`document-${DOC}`));
  expect(await screen.findByText("Биохими")).toBeOnTheScreen();
  expect(screen.getByText(/автоматаар уншсан ноорог/)).toBeOnTheScreen();
  expect(screen.getByText("Огноо: 2025.05.03")).toBeOnTheScreen(); // a day, no time
  expect(screen.getByText("! Ноорог — батлаагүй")).toBeOnTheScreen();
  expect(screen.getByText("88 мкмоль/л")).toBeOnTheScreen();
  expect(screen.getByText("Лавлах хэмжээ: 62 - 115")).toBeOnTheScreen();
  expect(screen.getByText(/Шалгах: шинжилгээ танигдсангүй/)).toBeOnTheScreen();
  expect(screen.queryByText("H")).toBeNull(); // the lab's own mark is not shown (rule 5)
  expect(screen.queryByText(/AI-аар/)).toBeNull();
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
