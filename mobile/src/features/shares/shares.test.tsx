import { fireEvent, renderRouter, screen, waitFor } from "expo-router/testing-library";
import { Alert } from "react-native";

import { clearAccessToken, setStatus } from "@/features/auth/session-store";
import { noticeKey } from "@/features/notices/notice-text";
import { resetActiveProfile, setActiveProfile } from "@/features/records/active-profile";
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
// the summary and export files: what was written and shared (no real file system here)
const mockShared: { name: string; size: number; mime: string }[] = [];
jest.mock("@/features/emergency/export-files", () => ({
  ...jest.requireActual("@/features/emergency/export-files"),
  writeForSharing: (_: unknown, bytes: Uint8Array, name: string) => ({ name, size: bytes.length }),
  shareFile: async (_: unknown, file: { name: string; size: number }, mime: string) => {
    mockShared.push({ ...file, mime });
    return "shared";
  },
}));
// linked to an EAS project in this file only (elsewhere: none, so no token is ever asked for)
jest.mock("expo-constants", () => ({
  __esModule: true,
  default: { expoConfig: { extra: { eas: { projectId: "project-1" } } }, easConfig: null },
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
// a profile shared with this user as a doctor
const PATIENT = {
  ...OWN,
  id: "00000000-0000-4000-8000-0000000000cc",
  full_name: "Дорж",
  access_level: "doctor",
};
const allGiven = ["terms", "privacy", "sensitive_data"].map((kind) => ({
  kind,
  current_version: "draft-2026-10",
  granted: true,
  granted_version: "draft-2026-10",
  at: "2026-10-01T00:00:00Z",
  required: true,
}));

let posts: { path: string; body: unknown }[] = [];
const record =
  (path: string, status = 204) =>
  async (request: Request) => {
    posts.push({ path, body: await request.json().catch(() => null) });
    return new Response(null, { status });
  };

const handlers: Record<string, Handler> = {
  "POST /api/v1/auth/refresh": () =>
    json(200, { access_token: "a1", token_type: "bearer", expires_in: 900, refresh_token: "r1" }),
  "GET /api/v1/me": () => json(200, { locale: "mn", display_name: "Бат Болд" }),
  "GET /api/v1/me/consents": () => json(200, allGiven),
  "GET /api/v1/me/notifications": () => json(200, []),
  "GET /api/v1/healthz": () => json(200, { status: "ok" }),
  "GET /api/v1/patients": () => json(200, [OWN, PATIENT]),
  "GET /api/v1/me/caregiver-invitations": () => json(200, []),
  "GET /api/v1/me/share-invitations": () =>
    json(200, [
      {
        id: "sinv-1",
        inviter_name: "Оюун",
        level: "doctor",
        access_days: 7,
        created_at: "2026-11-10T00:00:00Z",
        expires_at: "2026-11-24T00:00:00Z",
      },
    ]),
  "POST /api/v1/me/share-invitations/respond": record("respond"),
  "POST /api/v1/me/shares/leave": record("leave"),
  [`GET /api/v1/patients/${OWN.id}/shares`]: () =>
    json(200, {
      shares: [
        {
          user_id: "u-9",
          display_name: "Д. Ганбат",
          level: "doctor",
          since: "2026-11-01T00:00:00Z",
          expires_at: null,
          last_viewed_at: "2026-11-15T02:30:00Z",
        },
      ],
      invitations: [
        {
          id: "i-1",
          username: "nurse.b",
          level: "viewer",
          access_days: 1,
          created_at: "2026-11-16T00:00:00Z",
          expires_at: "2026-11-30T00:00:00Z",
        },
      ],
    }),
  [`GET /api/v1/patients/${OWN.id}/share-views`]: () =>
    json(200, [
      {
        user_id: "u-9",
        display_name: "Д. Ганбат",
        day: "2026-11-15",
        first_at: "2026-11-15T01:00:00Z",
        last_at: "2026-11-15T02:30:00Z",
      },
    ]),
  [`POST /api/v1/patients/${OWN.id}/share-invitations`]: record("invite", 202),
  [`DELETE /api/v1/patients/${OWN.id}/shares/u-9`]: record("end"),
  [`GET /api/v1/patients/${OWN.id}/summary.pdf`]: (request: Request) => {
    posts.push({ path: "summary", body: new URL(request.url).search });
    return new Response(new Uint8Array([37, 80, 68, 70]), {
      status: 200,
      headers: { "Content-Type": "application/pdf" },
    });
  },
  [`GET /api/v1/patients/${OWN.id}/export.fhir.json`]: () => json(200, { resourceType: "Bundle" }),
  "GET /api/v1/lab-tests": () =>
    json(200, [
      {
        code: "TAC",
        name_mn: "Такролимус",
        name_en: "Tacrolimus",
        canonical_unit: "ng/mL",
        category: "drug",
      },
      {
        code: "CREA",
        name_mn: "Креатинин",
        name_en: "Creatinine",
        canonical_unit: "µmol/L",
        category: "kidney",
      },
    ]),
  "POST /api/v1/me/doctor/targets": record("target", 201),
  "POST /api/v1/me/doctor/targets/end": record("target-end"),
  "POST /api/v1/me/doctor/notes": record("note", 201),
  "POST /api/v1/me/doctor/notes/remove": record("note-remove"),
  [`GET /api/v1/patients/${OWN.id}/share-links`]: () =>
    json(200, [
      {
        id: "l-1",
        scopes: ["summary", "labs"],
        date_from: null,
        date_to: null,
        created_at: "2026-11-15T00:00:00Z",
        expires_at: "2099-11-22T00:00:00Z",
        max_views: 3,
        view_count: 1,
        revoked_at: null,
        revoked_reason: null,
        last_viewed_at: "2026-11-16T03:00:00Z",
      },
      {
        id: "l-2",
        scopes: ["meds"],
        date_from: null,
        date_to: null,
        created_at: "2026-11-01T00:00:00Z",
        expires_at: "2026-11-02T00:00:00Z",
        max_views: null,
        view_count: 0,
        revoked_at: "2026-11-01T05:00:00Z",
        revoked_reason: "pin_locked",
        last_viewed_at: null,
      },
    ]),
  [`GET /api/v1/patients/${OWN.id}/share-links/l-1/views`]: () =>
    json(200, [{ opened_at: "2026-11-16T03:00:00Z" }]),
  [`POST /api/v1/patients/${OWN.id}/share-links`]: async (request: Request) => {
    posts.push({ path: "link", body: await request.json() });
    return json(201, {
      id: "l-3",
      token: "tok_abcdefghijklmnopqrstuvwxyz0123456789",
      pin: "123456",
      expires_at: "2026-11-25T00:00:00Z",
    });
  },
  [`DELETE /api/v1/patients/${OWN.id}/share-links/l-1`]: record("revoke-link"),
};
for (const p of [OWN, PATIENT]) {
  const base = `/api/v1/patients/${p.id}`;
  handlers[`GET ${base}/targets`] = () =>
    json(200, [
      {
        id: "t-1",
        test_code: "TAC",
        low: "5",
        high: "8",
        unit: "ng/mL",
        valid_from: "2026-10-01",
        valid_to: null,
        note: "Өглөөний тунгаас өмнө",
        set_by_name: "Д. Ганбат",
      },
    ]);
  handlers[`GET ${base}/doctor-notes`] = () =>
    json(200, [
      {
        id: "n-1",
        body: "Дараагийн үзлэг 12 сард.",
        created_at: "2026-11-10T02:00:00Z",
        author_name: "Д. Ганбат",
        mine: p.id === PATIENT.id,
      },
    ]);
  handlers[`GET ${base}/level-stats/TAC`] = () =>
    json(200, {
      test_code: "TAC",
      unit: "ng/mL",
      since: "2025-11-18",
      n: 6,
      mean: "6.4",
      sd: "1.2",
      cv_percent: "18.8",
      with_target: 6,
      in_target: 5,
      in_target_percent: "83.3",
      counted_from: "2026-02-01",
      bounds_left_out: 1,
      not_numeric_left_out: 0,
      other_unit_left_out: 0,
      no_date_left_out: 0,
      early_left_out: 2,
      duplicates_left_out: 0,
      same_day_left_out: 0,
      reason: null,
      values: [{ collected_on: "2026-11-01", value: "6.1", target_low: "5", target_high: "8" }],
    });
  handlers[`GET ${base}/transplants`] = () => json(200, []);
  handlers[`GET ${base}/medications`] = () => json(200, []);
  handlers[`GET ${base}/timezone`] = () =>
    json(200, { home: "Asia/Ulaanbaatar", current: "Asia/Ulaanbaatar", switches: [] });
  for (const kind of ["events", "contacts", "appointments", "questions", "vitals", "allergies"]) {
    handlers[`GET ${base}/${kind}`] = () => json(200, []);
  }
}

// confirmations: answered with the non-cancel button; what was asked is kept
let asked: string[] = [];
beforeEach(() => {
  queryClient.clear();
  clearAccessToken();
  setStatus("loading");
  resetActiveProfile();
  mockStore.clear();
  mockStore.set("lt.refresh", "r0");
  mockStore.set("lt.account", "00000000-0000-4000-8000-000000000001");
  posts = [];
  mockShared.length = 0;
  asked = [];
  jest.spyOn(Alert, "alert").mockImplementation((title, message, buttons) => {
    asked.push(`${title}|${message ?? ""}`);
    buttons?.find((b) => b.style !== "cancel")?.onPress?.();
  });
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

afterEach(() => {
  queryClient.clear();
  jest.restoreAllMocks();
});

async function openTab(name: RegExp) {
  await renderRouter("./src/app", { initialUrl: "/" });
  await fireEvent.press(await screen.findByRole("button", { name }));
}

test("the owner sees who has the profile, who opened it, and invites for a chosen time", async () => {
  await openTab(/^Профайл,/);
  await fireEvent.press(await screen.findByTestId("profile-shares"));
  expect(await screen.findAllByText("Д. Ганбат")).not.toHaveLength(0);
  expect(screen.getAllByText("Цуцлах хүртэл").length).toBeGreaterThan(1); // the card and the choice
  expect(screen.getByText(/^Сүүлд нээсэн: /)).toBeOnTheScreen();
  expect(await screen.findByText(/^Д\. Ганбат — /)).toBeOnTheScreen(); // a day it was opened
  expect(screen.getByText("Үзэгч · 24 цаг")).toBeOnTheScreen(); // the open invitation
  await fireEvent.changeText(screen.getByTestId("share-username"), " Dr.Bold ");
  await fireEvent.press(screen.getByRole("radio", { name: "Үзэгч" }));
  await fireEvent.press(screen.getByRole("radio", { name: "30 хоног" }));
  await fireEvent.press(screen.getByRole("button", { name: "Урих" }));
  expect(asked[0]).toMatch(/«dr.bold»-г Үзэгч эрхээр, 30 хоног хугацаатай/);
  await waitFor(() =>
    expect(posts).toContainEqual({
      path: "invite",
      body: { username: "dr.bold", level: "viewer", days: 30 },
    }),
  );
  expect(await screen.findByText(/Хүсэлтийг хүлээн авлаа/)).toBeOnTheScreen();
});

test("the owner revokes an access after confirming", async () => {
  await openTab(/^Профайл,/);
  await fireEvent.press(await screen.findByTestId("profile-shares"));
  await fireEvent.press(
    await screen.findByRole("button", { name: "Д. Ганбат-ийн эрхийг цуцлах уу?" }),
  );
  expect(asked[0]).toMatch(/буцаах боломжгүй/);
  await waitFor(() => expect(posts.map((p) => p.path)).toContain("end"));
});

test("an invited doctor sees who asks, as what and for how long, and accepts knowingly", async () => {
  await openTab(/^Тохиргоо,/);
  await fireEvent.press(await screen.findByTestId("settings-invitations"));
  expect(await screen.findByText("Оюун таныг Эмч эрхээр урьж байна")).toBeOnTheScreen();
  expect(screen.getByText("7 хоног")).toBeOnTheScreen();
  await fireEvent.press(screen.getByRole("button", { name: "Урилгыг зөвшөөрөх — Оюун" }));
  expect(asked[0]).toMatch(/нээсэн өдрүүд профайлын эзэнд харагдана/);
  await waitFor(() =>
    expect(posts).toContainEqual({
      path: "respond",
      body: { invitation_id: "sinv-1", accept: true },
    }),
  );
});

test("a doctor can step back from a shared profile, and cannot manage its sharing", async () => {
  setActiveProfile(PATIENT.id);
  await openTab(/^Профайл,/);
  await screen.findByTestId("profile-leave-share");
  expect(screen.queryByTestId("profile-shares")).toBeNull();
  await fireEvent.press(screen.getByTestId("profile-leave-share"));
  expect(asked[0]).toMatch(/шинээр урилга хүсэх/);
  await waitFor(() =>
    expect(posts).toContainEqual({ path: "leave", body: { patient_id: PATIENT.id } }),
  );
});

test("a doctor's or a viewer's invitation reads as such in the notices", () => {
  expect(noticeKey({ kind: "share_invite", title_key: "notification.share_invite" })).toBe(
    "kind.access_invite",
  );
  expect(noticeKey({ kind: "share_invite", title_key: "notification.caregiver_invite" })).toBe(
    "kind.share_invite",
  );
});

test("the owner makes a link with a QR code, sees the PIN once, and revokes a link", async () => {
  await openTab(/^Профайл,/);
  await fireEvent.press(await screen.findByTestId("profile-share-links"));
  expect(await screen.findByText("Идэвхтэй")).toBeOnTheScreen();
  expect(screen.getByText("1/3 удаа нээсэн")).toBeOnTheScreen();
  expect(screen.getByText(/PIN буруу оруулсан тул хаагдсан/)).toBeOnTheScreen();
  await fireEvent.press(screen.getByRole("button", { name: "Нээсэн цагуудыг харах" }));
  await fireEvent.press(screen.getByRole("button", { name: "Линкийг цуцлах" }));
  await waitFor(() => expect(posts.map((p) => p.path)).toContain("revoke-link"));

  // unchoose "Эм", choose "Шилжүүлэн суулгалт"; 30 days, 3 opens
  await fireEvent.press(screen.getByRole("checkbox", { name: "Эм" }));
  await fireEvent.press(screen.getByRole("checkbox", { name: "Шилжүүлэн суулгалт" }));
  await fireEvent.press(screen.getByRole("radio", { name: "30 хоног" }));
  await fireEvent.press(screen.getByRole("radio", { name: "3 удаа" }));
  await fireEvent.press(screen.getByRole("button", { name: "Линк үүсгэх" }));
  expect(asked.at(-1)).toMatch(
    /Хэсэг: Тойм, Шинжилгээний хариу, Шилжүүлэн суулгалт\. Хүчинтэй: 30 хоног/,
  );
  await waitFor(() =>
    expect(posts).toContainEqual({
      path: "link",
      body: {
        scopes: ["summary", "labs", "transplant"],
        days: 30,
        max_views: 3,
        date_from: null,
        date_to: null,
      },
    }),
  );
  expect(await screen.findByTestId("link-qr")).toBeOnTheScreen();
  expect(screen.getByTestId("link-url")).toHaveTextContent(
    `${apiBaseUrl}/s#tok_abcdefghijklmnopqrstuvwxyz0123456789`,
  );
  expect(screen.getByTestId("link-pin")).toHaveTextContent("123 456");
  await fireEvent.press(screen.getByRole("button", { name: "Болсон" }));
  expect(await screen.findByText("Шинэ линк")).toBeOnTheScreen();
  expect(screen.queryByTestId("link-pin")).toBeNull();
});

test("the owner reads the doctor's targets and notes, writes nothing, and sees no level numbers yet", async () => {
  await openTab(/^Профайл,/);
  await fireEvent.press(await screen.findByTestId("profile-doctor"));
  expect(await screen.findByText("5 – 8 ng/mL")).toBeOnTheScreen();
  expect(screen.getByText("Тогтоосон: Д. Ганбат")).toBeOnTheScreen();
  expect(screen.getByText("Такролимус")).toBeOnTheScreen();
  expect(await screen.findByText("Дараагийн үзлэг 12 сард.")).toBeOnTheScreen();
  // the explanation awaits the physician's review (Q12): no numbers for the patient yet
  expect(screen.queryByTestId("level-stats")).toBeNull();
  expect(screen.queryByText("Дундаж")).toBeNull();
  expect(screen.queryByRole("button", { name: "Зорилт хадгалах" })).toBeNull();
  expect(screen.queryByRole("button", { name: "Тэмдэглэл нэмэх" })).toBeNull();
  expect(screen.queryByRole("button", { name: "Тэмдэглэлийг устгах" })).toBeNull();
});

test("a doctor sets a target, ends one, and adds and removes a note", async () => {
  setActiveProfile(PATIENT.id);
  await openTab(/^Профайл,/);
  await fireEvent.press(await screen.findByTestId("profile-doctor"));
  expect(await screen.findByText("Стандарт хазайлт")).toBeOnTheScreen();
  expect(screen.getByText("18.8%")).toBeOnTheScreen();
  expect(screen.getByText("5/6 (83.3%)")).toBeOnTheScreen();
  expect(screen.getByText(/2 утгыг хассан: шилжүүлэн суулгалтаас 3 сарын дотор/)).toBeOnTheScreen();
  await fireEvent.press(screen.getByRole("button", { name: "Тоолсон 1 утгыг харах" }));
  expect(screen.getByText("6.1 ng/mL")).toBeOnTheScreen();
  await fireEvent.changeText(screen.getByTestId("target-search"), "креа");
  await fireEvent.press(await screen.findByRole("radio", { name: "Креатинин (µmol/L)" }));
  await fireEvent.changeText(screen.getByTestId("target-high"), "120,5");
  await fireEvent.press(screen.getByRole("button", { name: "Зорилт хадгалах" }));
  expect(asked.at(-1)).toMatch(/Креатинин: доод —, дээд 120,5 µmol\/L/);
  await waitFor(() =>
    expect(posts).toContainEqual({
      path: "target",
      body: expect.objectContaining({
        patient_id: PATIENT.id,
        test_code: "CREA",
        low: null,
        high: "120.5",
        note: null,
      }),
    }),
  );
  await fireEvent.press(screen.getByRole("button", { name: "Такролимус-ийн зорилтыг дуусгах" }));
  await waitFor(() => expect(posts.map((x) => x.path)).toContain("target-end"));
  await fireEvent.changeText(screen.getByTestId("note-body"), " Тунг эмч өөрчилнө. ");
  await fireEvent.press(screen.getByRole("button", { name: "Тэмдэглэл нэмэх" }));
  await waitFor(() =>
    expect(posts).toContainEqual({
      path: "note",
      body: { patient_id: PATIENT.id, body: "Тунг эмч өөрчилнө." },
    }),
  );
  await fireEvent.press(screen.getByRole("button", { name: "Тэмдэглэлийг устгах" }));
  await waitFor(() =>
    expect(posts).toContainEqual({ path: "note-remove", body: { note_id: "n-1" } }),
  );
});

test("the owner makes the summary PDF and the FHIR export, each straight to the share sheet", async () => {
  setActiveProfile(OWN.id);
  await openTab(/^Профайл,/);
  await fireEvent.press(await screen.findByTestId("profile-summary"));
  await fireEvent.press(await screen.findByRole("radio", { name: "Сүүлийн 12 сар" }));
  await fireEvent.press(screen.getByRole("radio", { name: "English" }));
  await fireEvent.press(screen.getByRole("button", { name: "PDF үүсгэх" }));
  await waitFor(() =>
    expect(mockShared).toContainEqual({
      name: "labtrack-summary.pdf",
      size: 4,
      mime: "application/pdf",
    }),
  );
  expect(posts).toContainEqual({ path: "summary", body: "?months=12&lang=en" });
  expect(screen.getByText(/шифрлэгдээгүй/)).toBeOnTheScreen();
  const fhir = screen.getByRole("button", { name: "FHIR (R4) файл авах" });
  await waitFor(() => expect(fhir).toBeEnabled());
  await fireEvent.press(fhir);
  await waitFor(() => expect(mockShared.map((f) => f.name)).toContain("labtrack-export-fhir.json"));
});

test("a doctor gets the summary PDF but not the owner's export", async () => {
  setActiveProfile(PATIENT.id);
  await openTab(/^Профайл,/);
  await fireEvent.press(await screen.findByTestId("profile-summary"));
  expect(await screen.findByRole("button", { name: "PDF үүсгэх" })).toBeOnTheScreen();
  expect(screen.queryByRole("button", { name: "JSON файл авах" })).toBeNull();
});
