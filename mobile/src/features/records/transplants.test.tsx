import { fireEvent, renderRouter, screen, waitFor } from "expo-router/testing-library";

import { clearAccessToken, setStatus } from "@/features/auth/session-store";
import { apiBaseUrl } from "@/lib/api-base";
import { queryClient } from "@/lib/query-client";

import { setWizardActive } from "./onboarding-store";

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

let patients: (typeof OWN)[] = [];
let transplants: Record<string, unknown>[] = [];
let transplantPosts: Record<string, unknown>[] = [];
let failNextTransplant = false;
const calls: string[] = [];

function stored(body: Record<string, unknown>) {
  return {
    ...body,
    id: "11111111-1111-4111-8111-111111111111",
    elapsed: { days: 2000, months: 66, years: 5, approximate: true },
    created_at: "2026-11-04T00:00:00Z",
    updated_at: null,
  };
}

const handlers: Record<string, Handler> = {
  "POST /api/v1/auth/refresh": () =>
    json(200, { access_token: "a1", token_type: "bearer", expires_in: 900, refresh_token: "r1" }),
  "GET /api/v1/me": () => json(200, { locale: "mn", display_name: "Бат Болд" }),
  "GET /api/v1/me/consents": () => json(200, allGiven),
  "GET /api/v1/me/notifications": () => json(200, []),
  "GET /api/v1/healthz": () => json(200, { status: "ok" }),
  "GET /api/v1/patients": () => json(200, patients),
  "POST /api/v1/patients": async (request) => {
    const body = (await request.json()) as { full_name: string };
    patients = [{ ...OWN, full_name: body.full_name }];
    return json(201, patients[0]);
  },
  [`GET /api/v1/patients/${OWN.id}/transplants`]: () => json(200, transplants),
  [`POST /api/v1/patients/${OWN.id}/transplants`]: async (request) => {
    const body = (await request.json()) as Record<string, unknown>;
    transplantPosts.push(body);
    if (failNextTransplant) {
      failNextTransplant = false;
      throw new TypeError("Network request failed");
    }
    transplants = [stored(body)];
    return json(201, transplants[0]);
  },
  [`PUT /api/v1/patients/${OWN.id}/transplants/11111111-1111-4111-8111-111111111111`]: async (
    request,
  ) => {
    const body = (await request.json()) as Record<string, unknown>;
    transplantPosts.push(body);
    transplants = [stored(body)];
    return json(200, transplants[0]);
  },
};

beforeEach(() => {
  queryClient.clear();
  clearAccessToken();
  setStatus("loading");
  setWizardActive(false);
  mockStore.clear();
  mockStore.set("lt.refresh", "r0");
  patients = [];
  transplants = [];
  transplantPosts = [];
  failNextTransplant = false;
  calls.length = 0;
  mockFetch.mockReset();
  mockFetch.mockImplementation(async (input: Request | string, init?: RequestInit) => {
    const request = typeof input === "string" ? new Request(input, init) : input;
    const key = `${request.method} ${request.url.slice(apiBaseUrl.length)}`;
    calls.push(key);
    const handler = handlers[key];
    if (!handler) return json(404, { code: "not_found", message_key: "error.not_found" });
    return handler(request);
  });
  globalThis.fetch = mockFetch as unknown as typeof fetch;
});

async function openTransplants() {
  await renderRouter("./src/app", { initialUrl: "/" });
  await fireEvent.press(await screen.findByRole("button", { name: /Профайл/ }));
  await fireEvent.press(await screen.findByTestId("profile-transplants"));
}

const press = async (name: string | RegExp) =>
  fireEvent.press(await screen.findByRole(/button|radio|link/, { name }));

test("first sign-in: the wizard records a transplant known to the month, then the app", async () => {
  await renderRouter("./src/app", { initialUrl: "/" });
  expect(await screen.findByLabelText("Ямар эрхтэн шилжүүлэн суулгуулсан бэ?")).toBeOnTheScreen();
  // nothing chosen: Continue says what is missing, nothing is sent
  await press("Үргэлжлүүлэх");
  expect(await screen.findByText(/Эрхтнээ сонгоно уу/)).toBeOnTheScreen();
  await press(/Бөөр$/);
  await press("Үргэлжлүүлэх");

  expect(await screen.findByText("Хэзээ шилжүүлэн суулгуулсан бэ?")).toBeOnTheScreen();
  await press("Он, сараар");
  fireEvent.changeText(await screen.findByLabelText("Он"), "2019");
  await press("Сар: Сонгоогүй");
  await press("5-р сар");
  await press("Үргэлжлүүлэх");

  expect(await screen.findByText("Хаана шилжүүлэн суулгуулсан бэ?")).toBeOnTheScreen();
  await press("Улс: Монгол");
  await press("Солонгос");
  await press("Үргэлжлүүлэх"); // no hospital yet
  expect(await screen.findByText(/Эмнэлгийн нэрийг бичнэ үү/)).toBeOnTheScreen();
  fireEvent.changeText(screen.getByLabelText("Эмнэлэг"), "Asan Medical Center");
  await press("Үргэлжлүүлэх");

  await press("Амьд донор — хамаатан");
  fireEvent.changeText(screen.getByLabelText("Донорын хамаарал (сонголттой)"), "ах");
  await press("Хадгалах"); // the optional details are not needed to save

  expect(await screen.findByText(/Өөр шилжүүлэн суулгалт/)).toBeOnTheScreen();
  expect(transplantPosts).toHaveLength(1);
  expect(transplantPosts[0]).toMatchObject({
    organ: "kidney",
    transplant_date: "2019-05-01",
    date_precision: "month",
    country: "KR",
    hospital: "Asan Medical Center",
    donor_type: "living_related",
    donor_relation: "ах",
    transplant_number: 1,
  });
  expect(String(transplantPosts[0]?.client_id)).toMatch(/^[0-9a-f-]{36}$/);
  // the own profile was created first, named as the account
  expect(patients[0]?.full_name).toBe("Бат Болд");

  await press("Үгүй, дууслаа");
  await waitFor(() => expect(screen.queryByText(/Өөр шилжүүлэн суулгалт/)).toBeNull());
});

test("a failed save is retried with the same client_id (never a duplicate)", async () => {
  patients = [OWN];
  failNextTransplant = true;
  await openTransplants();
  await press("Шилжүүлэн суулгалт нэмэх");
  await press(/Элэг$/);
  await press("Үргэлжлүүлэх");
  await press("Зөвхөн оноор");
  fireEvent.changeText(await screen.findByLabelText("Он"), "2015");
  await press("Үргэлжлүүлэх");
  fireEvent.changeText(await screen.findByLabelText("Эмнэлэг"), "Улсын нэгдүгээр төв эмнэлэг");
  await press("Үргэлжлүүлэх");
  await press("Хадгалах");
  expect(await screen.findByText(/холбогдож чадсангүй/)).toBeOnTheScreen();
  await press("Хадгалах");
  expect(await screen.findByText(/Өөр шилжүүлэн суулгалт/)).toBeOnTheScreen();
  expect(transplantPosts).toHaveLength(2);
  expect(transplantPosts[0]?.client_id).toBe(transplantPosts[1]?.client_id);
  expect(transplantPosts[1]).toMatchObject({
    transplant_date: "2015-01-01",
    date_precision: "year",
  });
});

test("skipping still creates the own profile, so the wizard does not come back", async () => {
  await renderRouter("./src/app", { initialUrl: "/" });
  // enabled once the account (whose name the profile takes) has loaded
  await waitFor(() =>
    expect(screen.getByRole("link", { name: "Одоохондоо алгасах" })).toBeEnabled(),
  );
  await press("Одоохондоо алгасах");
  await waitFor(() => expect(patients).toHaveLength(1));
  await waitFor(() =>
    expect(screen.queryByLabelText("Ямар эрхтэн шилжүүлэн суулгуулсан бэ?")).toBeNull(),
  );
  expect(transplantPosts).toHaveLength(0);
});

test("editing keeps the fields the form does not show", async () => {
  patients = [OWN];
  transplants = [
    stored({
      organ: "liver",
      organ_detail: null,
      transplant_date: "2020-03-15",
      date_precision: "day",
      country: "IN",
      city: null,
      hospital: "Apollo",
      surgeon: "Dr. R",
      transplant_number: 1,
      donor_type: "unknown",
      donor_relation: null,
      recipient_blood_type: null,
      donor_blood_type: null,
      abo_incompatible: true,
      cmv_donor: null,
      cmv_recipient: null,
      ebv_donor: "pos",
      ebv_recipient: null,
      hla_mismatch: null,
      primary_disease: null,
      pre_transplant_dialysis: null,
      induction_therapy: null,
      graft_status: "functioning",
      graft_status_date: null,
      graft_failure_reason: null,
      follow_up_center: null,
      follow_up_doctor: null,
      notes: null,
    }),
  ];
  await openTransplants();
  await press(/Элэг · 2020\.03\.15/);
  fireEvent.changeText(await screen.findByLabelText("Эмнэлэг"), "Apollo Chennai");
  await press("Хадгалах");
  await waitFor(() => expect(transplantPosts).toHaveLength(1));
  expect(transplantPosts[0]).toMatchObject({
    hospital: "Apollo Chennai",
    surgeon: "Dr. R",
    abo_incompatible: true,
    ebv_donor: "pos",
    transplant_date: "2020-03-15",
  });
});
