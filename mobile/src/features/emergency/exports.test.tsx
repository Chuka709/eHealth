import { fireEvent, renderRouter, screen, waitFor } from "expo-router/testing-library";

import { clearAccessToken, setStatus } from "@/features/auth/session-store";
import { apiBaseUrl } from "@/lib/api-base";
import { queryClient } from "@/lib/query-client";

import { cardText } from "./card-text";
import { clearExports, keepForSharing, shareFile, startExport } from "./export-files";
import type { EmergencyCard } from "./snapshot";
import { escapeHtml, walletCardHtml } from "./wallet-card";

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
jest.mock("expo-local-authentication", () => ({
  hasHardwareAsync: jest.fn(async () => false),
  isEnrolledAsync: jest.fn(async () => false),
  SecurityLevel: { NONE: 0, SECRET: 1, BIOMETRIC_WEAK: 2, BIOMETRIC_STRONG: 3 },
  getEnrolledLevelAsync: jest.fn(async () => 0),
  authenticateAsync: jest.fn(async () => ({ success: false })),
}));
// the file system as far as these files go: what exists, what was moved where, what was removed
const mockFs = { dirs: new Set<string>(), removed: [] as string[], failMove: false };
jest.mock("expo-file-system", () => {
  const join = (parts: unknown[]) =>
    parts.map((p) => (typeof p === "string" ? p : (p as { uri: string }).uri)).join("/");
  class Directory {
    uri: string;
    constructor(...parts: unknown[]) {
      this.uri = join(parts);
    }
    get exists() {
      return mockFs.dirs.has(this.uri);
    }
    create() {
      mockFs.dirs.add(this.uri);
    }
    delete() {
      mockFs.dirs.delete(this.uri);
      mockFs.removed.push(this.uri);
    }
  }
  class File {
    uri: string;
    exists = true;
    constructor(...parts: unknown[]) {
      this.uri = join(parts);
    }
    create() {}
    async write() {}
    async move(dir: { uri: string }) {
      if (mockFs.failMove) throw new Error("move failed");
      // a file inside a folder that was deleted is gone (as on the device)
      if (mockFs.removed.some((d) => this.uri.startsWith(`${d}/`))) throw new Error("no such file");
      this.uri = `${dir.uri}/${this.uri.split("/").pop()}`;
    }
    rename(name: string) {
      this.uri = `${this.uri.split("/").slice(0, -1).join("/")}/${name}`;
    }
    delete() {
      mockFs.removed.push(this.uri);
    }
  }
  return { Directory, File, Paths: { document: "doc", cache: new Directory("file:///cache") } };
});
jest.mock("expo-print", () => ({
  printToFileAsync: jest.fn(async () => ({ uri: "file:///cache/Print/abc.pdf", numberOfPages: 1 })),
}));
jest.mock("expo-sharing", () => ({
  isAvailableAsync: jest.fn(async () => true),
  shareAsync: jest.fn(async () => undefined),
}));
jest.mock("react-native-view-shot", () => ({
  captureRef: jest.fn(async () => "iVBORw0KGgo="),
}));

type Handler = () => Response;
const mockFetch = jest.fn<Promise<Response>, [Request]>();
const json = (status: number, body: unknown) =>
  new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });

const OWN_ID = "00000000-0000-4000-8000-0000000000aa";
const OWN = {
  id: OWN_ID,
  relation: "self",
  access_level: "owner",
  full_name: "Бат",
  birth_date: "1980-02-03",
  sex: "unknown",
  is_minor: false,
  consent_required: false,
  created_at: "2026-01-01T00:00:00Z",
};
const CARD: EmergencyCard = {
  patient: { full_name: "Бат", birth_date: "1980-02-03", sex: "male" },
  blood_type: "A+",
  blood_type_withheld: null,
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
      city: null,
      hospital: "Улсын нэгдүгээр төв эмнэлэг",
      follow_up_center: null,
      follow_up_doctor: null,
      recipient_blood_type: null,
      donor_blood_type: null,
      abo_incompatible: null,
      cmv_donor: null,
      cmv_recipient: null,
    },
  ],
  dosed_medications: [
    {
      category: "immunosuppressant",
      name: "Програф",
      brand: null,
      form: null,
      strength: "1 мг",
      dose: {
        effective_from: "2026-10-01",
        dose_amount: null,
        dose_unit: "mg",
        dose_unit_text: null,
        schedule: { type: "daily", times: [{ at: "08:00", amount: "2" }] },
        instructions: null,
      },
      upcoming_doses: [],
      planned_end_on: null,
    },
  ],
  other_medications: [],
  recently_stopped: [],
  no_known_allergies_on: null,
  steroid_card: null,
  allergies: [],
  contacts: [{ name: "Төв", relation: null, phone: "7000 1234", is_transplant_center: true }],
  generated_at: "2026-11-10T02:00:00Z",
};
const P = `/api/v1/patients/${OWN_ID}`;
const routes: Record<string, Handler> = {
  "/api/v1/auth/refresh": () =>
    json(200, { access_token: "a1", token_type: "bearer", expires_in: 900, refresh_token: "r1" }),
  "/api/v1/me": () => json(200, { locale: "mn", display_name: "Бат Болд" }),
  "/api/v1/me/consents": () =>
    json(
      200,
      ["terms", "privacy", "sensitive_data"].map((kind) => ({
        kind,
        current_version: "draft-2026-10",
        granted: true,
        granted_version: "draft-2026-10",
        at: "2026-10-01T00:00:00Z",
        required: true,
      })),
    ),
  "/api/v1/me/notifications": () => json(200, []),
  "/api/v1/patients": () => json(200, [OWN]),
  [`${P}/transplants`]: () => json(200, []),
  [`${P}/medications`]: () => json(200, []),
  [`${P}/appointments`]: () => json(200, []),
  [`${P}/timezone`]: () =>
    json(200, { home: "Asia/Ulaanbaatar", current: "Asia/Ulaanbaatar", switches: [] }),
  [`${P}/emergency-card`]: () => json(200, CARD),
};

const Print = jest.requireMock<{ printToFileAsync: jest.Mock }>("expo-print");
const Sharing = jest.requireMock<{ shareAsync: jest.Mock }>("expo-sharing");
const Shot = jest.requireMock<{ captureRef: jest.Mock }>("react-native-view-shot");

beforeEach(() => {
  queryClient.clear();
  clearAccessToken();
  setStatus("loading");
  mockStore.clear();
  mockStore.set("lt.refresh", "r0");
  mockStore.set("lt.account", "00000000-0000-4000-8000-000000000001");
  mockFs.dirs.clear();
  mockFs.removed = [];
  mockFs.failMove = false;
  Print.printToFileAsync.mockClear();
  Sharing.shareAsync.mockClear();
  Shot.captureRef.mockClear();
  mockFetch.mockReset();
  mockFetch.mockImplementation(async (input: Request | string, init?: RequestInit) => {
    const request = typeof input === "string" ? new Request(input, init) : input;
    const path = request.url.slice(apiBaseUrl.length).split("?")[0];
    return routes[path]?.() ?? json(200, { status: "ok" });
  });
  globalThis.fetch = mockFetch as unknown as typeof fetch;
});

afterEach(() => queryClient.clear());

const lines = (text: ReturnType<typeof cardText>) =>
  [...text.front, ...text.back].flatMap((s) => [s.heading ?? "", ...s.lines]);

test("the card's text says the same as the card screen, in either language", () => {
  const mn = lines(cardText(CARD, "mn"));
  expect(mn).toContain("Нэр: Бат");
  expect(mn).toContain("Програф · 1 мг (Дархлаа дарангуйлагч): 08:00 · 2 мг");
  expect(mn).toContain("Харшлын мэдээлэл оруулаагүй — харшилгүй гэсэн үг биш.");
  expect(mn.some((l) => l.includes("лабораторийн шинжилгээгээр"))).toBe(true);
  const en = lines(cardText(CARD, "en"));
  expect(en).toContain("No allergy information entered — this does not mean no allergies.");
  expect(en).toContain("I take immunosuppressant medicines regularly.");
});

test("the wallpaper leaves out the name and date of birth unless chosen", () => {
  const out = lines(cardText(CARD, "mn", { name: false, birthDate: false }));
  expect(out.some((l) => l.includes("Бат"))).toBe(false);
  expect(out.some((l) => l.includes("1980"))).toBe(false);
  expect(out).toContain("Програф · 1 мг (Дархлаа дарангуйлагч): 08:00 · 2 мг");
});

test("the wallet card escapes what the user typed and loads nothing from outside", () => {
  const card = {
    ...CARD,
    allergies: [{ substance: '<img src=x onerror="alert(1)">', reaction: null, severity: null }],
  };
  const html = walletCardHtml(card);
  expect(html).not.toContain("<img");
  expect(html).toContain(escapeHtml('<img src=x onerror="alert(1)">'));
  // the escaped text may say "src=", but no tag can: nothing is fetched or run
  expect(html).not.toMatch(/https?:\/\/|<img|<script|<link|<iframe/);
  // both languages, one strip each
  expect(html).toContain('lang="mn"');
  expect(html).toContain('lang="en"');
  expect(html).toContain("Яаралтай тусламжийн карт");
  expect(html).toContain("Emergency card");
});

async function openCard() {
  await renderRouter("./src/app", { initialUrl: "/" });
  await fireEvent.press(
    await screen.findByRole("button", { name: "Яаралтай тусламжийн карт нээх" }),
  );
  await screen.findByText("Нэр: Бат");
}

test("the wallet PDF is made on the phone and leaves only through the share sheet", async () => {
  await openCard();
  await fireEvent.press(screen.getByRole("button", { name: /Түрийвчний картыг PDF-ээр/ }));
  await waitFor(() => expect(Sharing.shareAsync).toHaveBeenCalledTimes(1));
  expect(Print.printToFileAsync).toHaveBeenCalledTimes(1);
  const [uri, options] = Sharing.shareAsync.mock.calls[0];
  // a fixed name in the export folder: no name, no id in the path
  expect(uri).toBe("file:///cache/emergency-export/emergency-card.pdf");
  expect(options).toMatchObject({ mimeType: "application/pdf" });
  // no request carried the card anywhere
  const posts = mockFetch.mock.calls.filter(([r]) => r.method !== "GET");
  expect(posts.filter(([r]) => !r.url.endsWith("/auth/refresh"))).toEqual([]);
});

test("the wallpaper: name off by default, previewed as saved, shared, never put in the gallery", async () => {
  await openCard();
  await fireEvent.press(screen.getByTestId("emergency-wallpaper"));
  expect(await screen.findByText(/утсыг барьсан хэн ч/)).toBeOnTheScreen();
  const preview = () => screen.getByLabelText(/Яаралтай тусламжийн карт\./);
  expect(preview().props.accessibilityLabel).not.toContain("Бат");
  await fireEvent(screen.getByTestId("wallpaper-name"), "valueChange", true);
  await waitFor(() => expect(preview().props.accessibilityLabel).toContain("Нэр: Бат"));
  expect(screen.getByText(/Хуваалцахаасаа өмнө/)).toBeOnTheScreen();
  await fireEvent.press(screen.getByRole("button", { name: "Зургийг хуваалцах, хадгалах" }));
  await waitFor(() => expect(Sharing.shareAsync).toHaveBeenCalledTimes(1));
  expect(Shot.captureRef).toHaveBeenCalledTimes(1);
  // taken as base64 and written into the export folder: no view-shot tmpfile anywhere
  expect(Shot.captureRef.mock.calls[0][1]).toMatchObject({ result: "base64" });
  expect(Sharing.shareAsync.mock.calls[0][0]).toBe(
    "file:///cache/emergency-export/emergency-wallpaper.png",
  );
  expect(Sharing.shareAsync.mock.calls[0][1]).toMatchObject({ mimeType: "image/png" });
});

test("Medical ID: the steps and the card's text to copy by hand", async () => {
  await openCard();
  await fireEvent.press(screen.getByTestId("emergency-medical-id"));
  expect(await screen.findByText("iPhone — Medical ID")).toBeOnTheScreen();
  expect(screen.getByText("Android — Яаралтай мэдээлэл")).toBeOnTheScreen();
  const text = screen.getByTestId("medical-id-text");
  expect(text.props.selectable).toBe(true);
  expect(text.props.children).toContain("Програф · 1 мг");
});

test("exported files are removed: the export folder and expo-print's own", () => {
  mockFs.dirs.add("file:///cache/emergency-export");
  mockFs.dirs.add("file:///cache/Print");
  clearExports();
  expect(mockFs.dirs.size).toBe(0);
  expect(mockFs.removed).toEqual(["file:///cache/emergency-export", "file:///cache/Print"]);
});

test("an export that outlives its session is dropped: no file kept, no share sheet", async () => {
  const session =
    jest.requireActual<typeof import("@/features/auth/session")>("@/features/auth/session");
  const ticket = startExport();
  const later = jest.spyOn(session, "currentEpoch").mockReturnValue(ticket.epoch + 1);
  try {
    const file = await keepForSharing(ticket, "file:///cache/Print/abc.pdf", "emergency-card.pdf");
    expect(file).toBeNull();
    expect(mockFs.removed).toContain("file:///cache/Print/abc.pdf");
    expect(await shareFile(ticket, file, "application/pdf")).toBe("dropped");
    expect(Sharing.shareAsync).not.toHaveBeenCalled();
  } finally {
    later.mockRestore();
  }
});

test("a failed move leaves no source file behind", async () => {
  mockFs.failMove = true;
  await expect(
    keepForSharing(startExport(), "file:///cache/Print/abc.pdf", "emergency-card.pdf"),
  ).rejects.toThrow("move failed");
  expect(mockFs.removed).toContain("file:///cache/Print/abc.pdf");
});

test("the wallet card page forbids every outside load (CSP)", () => {
  expect(walletCardHtml(CARD)).toContain("default-src 'none'");
});

test("blood details and a recent stop reach the printed text, but never the wallpaper", () => {
  const card: EmergencyCard = {
    ...CARD,
    transplants: CARD.transplants.map((tr) => ({
      ...tr,
      recipient_blood_type: "A+",
      donor_blood_type: "O+",
      abo_incompatible: true,
      cmv_donor: "pos",
      cmv_recipient: "unknown",
    })),
    recently_stopped: [
      { name: "Програф", brand: null, stopped_on: "2026-11-01" },
      { name: "Сандиммун", brand: null, stopped_on: "2026-11-10" },
    ],
  };
  const printed = lines(cardText(card, "mn"));
  expect(printed).toContain("Цусны бүлэг: хүлээн авагч A+, донор O+");
  expect(printed).toContain("CMV: донор эерэг (+) / хүлээн авагч тодорхойгүй");
  const stops = printed.filter((l) => l.endsWith("эхлэн уугаагүй"));
  expect(stops).toEqual([
    "Сандиммун — 2026.11.10-ноос эхлэн уугаагүй", // the latest stop first
    "Програф — 2026.11.01-ноос эхлэн уугаагүй",
  ]);
  const wallpaper = lines(
    cardText(card, "mn", { name: false, birthDate: false, bloodDetails: false }),
  );
  expect(wallpaper.some((l) => l.startsWith("Цусны бүлэг: хүлээн авагч"))).toBe(false);
  expect(wallpaper.some((l) => l.startsWith("CMV"))).toBe(false);
  // after a stem-cell transplant the recorded type is the one before it (H17)
  const hsct = lines(
    cardText(
      { ...card, transplants: card.transplants.map((t) => ({ ...t, organ: "hsct" })) },
      "mn",
    ),
  );
  expect(hsct.some((l) => l.startsWith("Цусны бүлэг шилжүүлэн суулгахаас өмнө:"))).toBe(true);
});
