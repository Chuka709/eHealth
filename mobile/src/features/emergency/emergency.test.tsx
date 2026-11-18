import { router } from "expo-router";
import { act, fireEvent, renderRouter, screen, waitFor } from "expo-router/testing-library";

import { clearAccessToken, setStatus } from "@/features/auth/session-store";
import { apiBaseUrl } from "@/lib/api-base";
import { localStore } from "@/lib/local-store";
import { dropPersistedHealthData } from "@/lib/persist";
import { queryClient } from "@/lib/query-client";

import { dialable } from "./emergency-card-view";
import { readSnapshot } from "./snapshot";

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
  birth_date: "1980-02-03",
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
const dose = (amount: string, from: string) => ({
  effective_from: from,
  dose_amount: null,
  dose_unit: "mg",
  dose_unit_text: null,
  schedule: { type: "daily", times: [{ at: "08:00", amount }] },
  instructions: null,
});
const CARD = {
  patient: { full_name: "Бат", birth_date: "1980-02-03", sex: "male" },
  blood_type: null,
  blood_type_withheld: "conflict",
  transplants: [
    {
      organ: "kidney",
      organ_detail: null,
      transplant_date: "2021-06-14",
      date_precision: "day",
      elapsed: { days: 1975, months: 64, years: 5, approximate: false },
      transplant_number: 1,
      graft_status: "functioning",
      country: "MN",
      city: "Улаанбаатар",
      hospital: "Улсын нэгдүгээр төв эмнэлэг",
      follow_up_center: null,
      follow_up_doctor: null,
      recipient_blood_type: "A+",
      donor_blood_type: "O+",
      abo_incompatible: true,
      cmv_donor: "pos",
      cmv_recipient: "neg",
    },
  ],
  dosed_medications: [
    {
      category: "corticosteroid",
      name: "Преднизолон",
      brand: null,
      form: null,
      strength: "5 мг",
      dose: dose("10", "2026-10-01"),
      upcoming_doses: [dose("7,5", "2026-11-20")],
      planned_end_on: null,
    },
  ],
  other_medications: [{ name: "Витамин Д", brand: null }],
  recently_stopped: [{ name: "Такролимус", brand: "Програф", stopped_on: "2026-11-08" }],
  allergies: [],
  no_known_allergies_on: null,
  steroid_card: null,
  contacts: [{ name: "Төв", relation: null, phone: "7000 1234", is_transplant_center: true }],
  generated_at: "2026-11-10T02:00:00Z",
};

let cardAnswer: () => Response | Promise<Response> = () => json(200, CARD);

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
  [`GET ${P}/appointments`]: () => json(200, []),
  [`GET ${P}/timezone`]: () =>
    json(200, { home: "Asia/Ulaanbaatar", current: "Asia/Ulaanbaatar", switches: [] }),
  [`GET ${P}/emergency-card`]: () => cardAnswer(),
};

beforeEach(async () => {
  await dropPersistedHealthData(); // the open store outlives a test (sign-out empties it in the app)
  queryClient.clear();
  clearAccessToken();
  setStatus("loading");
  mockStore.clear();
  mockStore.set("lt.refresh", "r0");
  mockStore.set("lt.account", "00000000-0000-4000-8000-000000000001");
  cardAnswer = () => json(200, CARD);
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

async function openCard() {
  await renderRouter("./src/app", { initialUrl: "/" });
  await fireEvent.press(
    await screen.findByRole("button", { name: "Яаралтай тусламжийн карт нээх" }),
  );
  await screen.findByText("Би шилжүүлэн суулгалт хийлгэсэн.");
}

// a later visit: back to Home and 🆘 again (queries removed first, as after a cold start)
async function reopen() {
  await act(async () => router.back());
  await fireEvent.press(
    await screen.findByRole("button", { name: "Яаралтай тусламжийн карт нээх" }),
  );
}

// the saved copy once it is written (polled: waitFor with an async check deadlocks act())
async function saved(expectNone = false) {
  for (let i = 0; i < 50; i += 1) {
    const card = await readSnapshot(OWN.id);
    if (expectNone ? card === null : card !== null) return card;
    await new Promise((resolve) => setTimeout(resolve, 100));
  }
  return expectNone ? "still saved" : null;
}

const offline = () => {
  throw new TypeError("Network request failed");
};

test("🆘 on Home opens the card as the server assembled it (H17)", async () => {
  await openCard();
  expect(screen.getByText("Нэр: Бат")).toBeOnTheScreen();
  expect(screen.getByText("Төрсөн огноо: 1980.02.03")).toBeOnTheScreen();
  // a doubtful blood type is not shown, and says why
  expect(
    screen.getByText("Бүртгэлд зөрүүтэй тул харуулаагүй. Лабораторид тодорхойлно уу."),
  ).toBeOnTheScreen();
  expect(screen.queryByText(/Цус сэлбэхийн өмнө/)).toBeNull(); // only with a shown type
  expect(screen.getByText(/Бөөр · 2021\.06\.14/)).toBeOnTheScreen();
  expect(screen.getByText("Преднизолон · 5 мг")).toBeOnTheScreen();
  expect(screen.getByText("Кортикостероид")).toBeOnTheScreen();
  expect(screen.getByText("08:00 · 10 мг")).toBeOnTheScreen();
  expect(screen.getByText("2026.11.20 өдрөөс эхлэх тун: 08:00 · 7,5 мг")).toBeOnTheScreen();
  expect(screen.getByText(/одоогийн жортой зөрж болно/)).toBeOnTheScreen();
  // a corticosteroid alone does not claim immunosuppression
  expect(screen.queryByText("Дархлаа дарангуйлах эм тогтмол уудаг.")).toBeNull();
  expect(screen.getByText("Бусад эм: Витамин Д")).toBeOnTheScreen();
  // for blood products (Q35) and a recent stop (Q37), each as recorded
  // records that disagree (this card's blood type is withheld): the type before the transplant
  expect(
    screen.getByText(/^Цусны бүлэг шилжүүлэн суулгахаас өмнө: хүлээн авагч A\+, донор O\+/),
  ).toBeOnTheScreen();
  expect(screen.getByText(/^ABO таарахгүй \(ABO-incompatible\).*цусны банкинд/)).toBeOnTheScreen();
  expect(screen.getByText("CMV: донор эерэг (+) / хүлээн авагч сөрөг (−)")).toBeOnTheScreen();
  expect(
    screen.getByText("Такролимус (Програф) — 2026.11.08-ноос эхлэн уугаагүй"),
  ).toBeOnTheScreen();
  // none recorded is never "no allergies"
  expect(
    screen.getByText("Харшлын мэдээлэл оруулаагүй — харшилгүй гэсэн үг биш."),
  ).toBeOnTheScreen();
  expect(screen.getByRole("button", { name: "Залгах — Төв" })).toBeOnTheScreen();
  expect(screen.getByText("Шинэчилсэн: 2026.11.10 10:00")).toBeOnTheScreen();
  expect(screen.queryByText(/Утсанд хадгалсан хувилбар/)).toBeNull();
});

test("a confirmed no known allergies and the steroid card mark are shown as recorded (Q39, Q36)", async () => {
  cardAnswer = () =>
    json(200, {
      ...CARD,
      no_known_allergies_on: "2026-11-18",
      steroid_card: { marked_on: "2026-11-17", by_doctor: true },
    });
  await openCard();
  expect(
    screen.getByText("Мэдэгдэж буй харшилгүй (өөрөө баталсан, 2026.11.18)."),
  ).toBeOnTheScreen();
  expect(screen.queryByText(/Харшлын мэдээлэл оруулаагүй/)).toBeNull();
  expect(screen.getByText(/Стероидын яаралтай карт: .*бөөрний дээд булчирхай/)).toBeOnTheScreen();
  expect(screen.getByText("Эмч тэмдэглэсэн (2026.11.17).")).toBeOnTheScreen();
});

test("the card is saved encrypted and opens offline, marked as the saved copy", async () => {
  await openCard();
  expect(await saved()).toEqual(CARD);
  // the store keeps no plain copy: only the encrypted store holds it, under its own key
  const keys = (await localStore()).getAllKeys();
  expect(keys.filter((k) => k.startsWith("snapshot.emergency-card."))).toHaveLength(1);
  expect(keys.some((k) => k.includes("Бат"))).toBe(false);

  cardAnswer = offline;
  queryClient.removeQueries({ queryKey: ["emergency-card"] });
  await reopen();
  expect(await screen.findByText("Нэр: Бат")).toBeOnTheScreen();
  expect(
    await screen.findByText(/Утсанд хадгалсан хувилбар \(2026\.11\.10 10:00\)/),
  ).toBeOnTheScreen();
});

test("offline with nothing saved says so, never an empty card", async () => {
  cardAnswer = offline;
  await renderRouter("./src/app", { initialUrl: "/" });
  await fireEvent.press(
    await screen.findByRole("button", { name: "Яаралтай тусламжийн карт нээх" }),
  );
  expect(await screen.findByText(/Карт утсан дээр хараахан хадгалагдаагүй/)).toBeOnTheScreen();
  expect(screen.queryByText(/Харшлын мэдээлэл/)).toBeNull();
});

test("when access ends the saved copy leaves the phone", async () => {
  await openCard();
  expect(await saved()).not.toBeNull();
  cardAnswer = () =>
    json(404, { code: "patient.not_found", message_key: "error.patient.not_found" });
  queryClient.removeQueries({ queryKey: ["emergency-card"] });
  await reopen();
  expect(await saved(true)).toBeNull();
  expect(screen.queryByText("Нэр: Бат")).toBeNull();
});

test("the card can be shown in English for a team abroad", async () => {
  await openCard();
  await fireEvent.press(screen.getByRole("button", { name: "Show the card in English" }));
  expect(await screen.findByText("I have had a transplant.")).toBeOnTheScreen();
  expect(screen.getByText("Allergies")).toBeOnTheScreen();
  expect(screen.getByText("Planned from 2026.11.20: 08:00 · 7,5 mg")).toBeOnTheScreen();
  await fireEvent.press(screen.getByRole("button", { name: "Картыг монголоор харуулах" }));
  expect(await screen.findByText("Би шилжүүлэн суулгалт хийлгэсэн.")).toBeOnTheScreen();
});

test("a withdrawn consent drops the saved card with the cache", async () => {
  await openCard();
  expect(await saved()).not.toBeNull();
  await dropPersistedHealthData();
  expect(await readSnapshot(OWN.id)).toBeNull();
  // and from memory: re-granting the consent must not bring the dropped card back
  expect(queryClient.getQueryData(["emergency-card", OWN.id])).toBeUndefined();
  expect(queryClient.getQueryData(["emergency-card", OWN.id, "saved"])).toBeUndefined();
});

test("a card on screen disappears when access ends while it is open", async () => {
  await openCard();
  expect(await saved()).not.toBeNull();
  cardAnswer = () => json(403, { code: "consent.required", message_key: "error.consent.required" });
  await act(async () => {
    await queryClient.refetchQueries({ queryKey: ["emergency-card", OWN.id], exact: true });
  });
  expect(await saved(true)).toBeNull();
  await waitFor(() => expect(screen.queryByText("Нэр: Бат")).toBeNull());
  // a later retry that fails for another reason must not bring back the card held in memory
  cardAnswer = () => json(503, { code: "unavailable", message_key: "error.internal" });
  await act(async () => {
    await queryClient.refetchQueries({ queryKey: ["emergency-card", OWN.id], exact: true });
  });
  expect(screen.queryByText("Нэр: Бат")).toBeNull();
});

test("only digits and a leading + are dialled", () => {
  expect(dialable("+976 9911-2233")).toBe("+97699112233");
  expect(dialable("7000 1234;,*#")).toBe("70001234");
  expect(dialable("12+34")).toBe("1234");
  expect(dialable("--")).toBeNull();
});
