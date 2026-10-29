import { act, fireEvent, renderRouter, screen } from "expo-router/testing-library";
import type { ReactNode } from "react";
import { AccessibilityInfo, Linking } from "react-native";

import { apiBaseUrl } from "@/lib/api-base";

import { setPendingActivationToken } from "./activation-link";
import { refreshSession } from "./session";
import { getStatus, setStatus } from "./session-store";

const mockStore = new Map<string, string>();
const mockCamera = { qr: "", permission: { granted: true, canAskAgain: true } };

jest.mock("expo-secure-store", () => ({
  WHEN_UNLOCKED_THIS_DEVICE_ONLY: 6,
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
jest.mock("expo-screen-capture", () => ({
  usePreventScreenCapture: jest.fn(),
  enableAppSwitcherProtectionAsync: jest.fn(async () => undefined),
  disableAppSwitcherProtectionAsync: jest.fn(async () => undefined),
}));
jest.mock("expo-device", () => ({ modelName: "Pixel 8" }));
jest.mock("expo-camera", () => {
  const { Pressable: P } = jest.requireActual<typeof import("react-native")>("react-native");
  return {
    useCameraPermissions: () => [mockCamera.permission, jest.fn()],
    // Stand-in camera: pressing it "scans" whatever mockCamera.qr holds.
    CameraView: ({
      onBarcodeScanned,
    }: {
      onBarcodeScanned: (result: { data: string }) => void;
    }): ReactNode => (
      <P
        accessibilityRole="button"
        accessibilityLabel="scan"
        onPress={() => onBarcodeScanned({ data: mockCamera.qr })}
      />
    ),
  };
});
jest.mock("@/lib/support", () => ({ supportPhone: "7011 0000", supportPhoneUrl: "tel:70110000" }));
const openURL = jest.spyOn(Linking, "openURL").mockResolvedValue(undefined);
jest.spyOn(AccessibilityInfo, "announceForAccessibility");

type Handler = (request: Request) => Promise<Response> | Response;
const mockFetch = jest.fn<Promise<Response>, [Request]>();
const json = (status: number, body: unknown) =>
  new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
const err = (status: number, code: string) => json(status, { code, message_key: `error.${code}` });

function route(handlers: Record<string, Handler>) {
  mockFetch.mockImplementation(async (input: Request | string, init?: RequestInit) => {
    const request = typeof input === "string" ? new Request(input, init) : input;
    const handler = handlers[request.url.slice(apiBaseUrl.length)];
    if (!handler) return json(200, { status: "ok" });
    return handler(request);
  });
}
const bodies = (path: string) =>
  Promise.all(
    mockFetch.mock.calls
      .filter(([request]) => request.url === `${apiBaseUrl}${path}`)
      .map(([request]) => request.clone().json() as Promise<Record<string, unknown>>),
  );

const token = `${"T".repeat(30)}_-abc123XYZ90`;
const link = `labtrack://activate#${token}`;

beforeEach(() => {
  mockStore.clear();
  mockFetch.mockReset();
  route({});
  globalThis.fetch = mockFetch as unknown as typeof fetch;
  mockCamera.qr = "";
  mockCamera.permission = { granted: true, canAskAgain: true };
  setStatus("loading");
});

const app = (initialUrl = "/") => renderRouter("./src/app", { initialUrl });
// External links cannot open /login (+native-intent), so go there the way a user does.
async function openLogin() {
  await app("/");
  await fireEvent.press(await screen.findByRole("button", { name: "Нэвтрэх" }));
}

test("signed out: welcome offers activation and sign-in", async () => {
  await app();
  expect(await screen.findByText("LabTrack MN-д тавтай морил")).toBeOnTheScreen();
  await fireEvent.press(screen.getByRole("button", { name: "Нэвтрэх" }));
  expect(screen).toHavePathname("/login");
});

describe("activation", () => {
  test("rejects a foreign QR, then sets the password and goes to sign-in", async () => {
    route({ "/api/v1/auth/activate": () => new Response(null, { status: 204 }) });
    await app("/activate");
    mockCamera.qr = "https://evil.example/activate";
    await fireEvent.press(await screen.findByRole("button", { name: "scan" }));
    expect(screen.getByText(/идэвхжүүлэх код биш/)).toBeOnTheScreen();

    mockCamera.qr = link;
    await fireEvent.press(screen.getByRole("button", { name: "scan" }));
    await fireEvent.changeText(await screen.findByLabelText("Хэрэглэгчийн нэр"), " Bat.01 ");
    const password = screen.getByLabelText("Шинэ нууц үг");
    await fireEvent.changeText(password, "short");
    await fireEvent.changeText(screen.getByLabelText("Нууц үгээ давтах"), "other");
    await fireEvent.press(screen.getByRole("button", { name: "Нууц үг тохируулах" }));
    expect(await screen.findByText(/дор хаяж 10 тэмдэгт байна/)).toBeOnTheScreen();
    expect(screen.getByText(/Нууц үгүүд таарахгүй байна/)).toBeOnTheScreen();
    expect(await bodies("/api/v1/auth/activate")).toHaveLength(0);

    const strong = "ногоон-цонх-гурван-морь";
    await fireEvent.changeText(password, strong);
    await fireEvent.changeText(screen.getByLabelText("Нууц үгээ давтах"), strong);
    expect(await screen.findByLabelText(/маш хүчтэй/)).toBeOnTheScreen();
    await fireEvent.press(screen.getByRole("button", { name: "Нууц үг тохируулах" }));

    expect(await screen.findByText(/Аккаунт идэвхжлээ/)).toBeOnTheScreen();
    expect(screen).toHavePathname("/login");
    expect(await bodies("/api/v1/auth/activate")).toEqual([
      { token, username: "bat.01", new_password: strong },
    ]);
  });

  test("a link token skips the scanner; server policy errors show under the field", async () => {
    setPendingActivationToken(token);
    route({ "/api/v1/auth/activate": () => err(422, "password.too_weak") });
    await app("/activate");
    const strong = "aaaaaaaaaaaa";
    await fireEvent.changeText(await screen.findByLabelText("Хэрэглэгчийн нэр"), "bat");
    await fireEvent.changeText(screen.getByLabelText("Шинэ нууц үг"), strong);
    await fireEvent.changeText(screen.getByLabelText("Нууц үгээ давтах"), strong);
    await fireEvent.press(screen.getByRole("button", { name: "Нууц үг тохируулах" }));
    expect(await screen.findByText(/хэт амархан таагдана/)).toBeOnTheScreen();
    expect(screen).toHavePathname("/activate");
  });

  test("an expired code asks for a new one", async () => {
    setPendingActivationToken(token);
    route({ "/api/v1/auth/activate": () => err(400, "auth.activation_invalid") });
    await app("/activate");
    const strong = "ногоон-цонх-гурван-морь";
    await fireEvent.changeText(await screen.findByLabelText("Хэрэглэгчийн нэр"), "bat");
    await fireEvent.changeText(screen.getByLabelText("Шинэ нууц үг"), strong);
    await fireEvent.changeText(screen.getByLabelText("Нууц үгээ давтах"), strong);
    await fireEvent.press(screen.getByRole("button", { name: "Нууц үг тохируулах" }));
    expect(await screen.findByText(/кодын хугацаа дууссан/)).toBeOnTheScreen();
    await fireEvent.press(screen.getByRole("button", { name: "Өөр код уншуулах" }));
    expect(await screen.findByRole("button", { name: "scan" })).toBeOnTheScreen();
  });
});

describe("sign-in", () => {
  test("sends the trusted-device token and opens the app", async () => {
    mockStore.set("lt.device", "device-1");
    route({
      "/api/v1/auth/login": () =>
        json(200, {
          access_token: "a1",
          token_type: "bearer",
          expires_in: 900,
          refresh_token: "r1",
        }),
    });
    await openLogin();
    await fireEvent.changeText(await screen.findByLabelText("Хэрэглэгчийн нэр"), " Bat.01 ");
    await fireEvent.changeText(screen.getByLabelText("Нууц үг"), "pw-123");
    await fireEvent.press(screen.getByRole("button", { name: "Нэвтрэх" }));

    expect(await screen.findByText("Системийн төлөв")).toBeOnTheScreen();
    expect(getStatus()).toBe("signedIn");
    expect(mockStore.get("lt.refresh")).toBe("r1");
    expect(await bodies("/api/v1/auth/login")).toEqual([
      {
        username: "bat.01",
        password: "pw-123",
        platform: expect.stringMatching(/^(ios|android)$/),
        device_name: "Pixel 8",
        device_token: "device-1",
      },
    ]);
  });

  test("shows the single generic error and requires both fields", async () => {
    route({ "/api/v1/auth/login": () => err(401, "auth.invalid_credentials") });
    await openLogin();
    await fireEvent.press(await screen.findByRole("button", { name: "Нэвтрэх" }));
    expect(await screen.findAllByText(/Энэ талбарыг бөглөнө үү/)).toHaveLength(2);

    await fireEvent.changeText(screen.getByLabelText("Хэрэглэгчийн нэр"), "bat");
    await fireEvent.changeText(screen.getByLabelText("Нууц үг"), "wrong");
    await fireEvent.press(screen.getByRole("button", { name: "Нэвтрэх" }));
    expect(await screen.findByText("Нэр эсвэл нууц үг буруу байна.")).toBeOnTheScreen();
    expect(getStatus()).toBe("signedOut");
  });

  test("password can be revealed", async () => {
    await openLogin();
    const field = await screen.findByLabelText("Нууц үг");
    expect(field.props.secureTextEntry).toBe(true);
    await fireEvent.press(screen.getByRole("button", { name: "Нууц үгийг харуулах" }));
    expect(screen.getByLabelText("Нууц үг").props.secureTextEntry).toBe(false);
  });

  test("forgot password tells the user to call the admin", async () => {
    await openLogin();
    await fireEvent.press(await screen.findByText("Нууц үгээ мартсан уу?"));
    expect(await screen.findByText(/зөвхөн админ сэргээнэ/)).toBeOnTheScreen();
    await fireEvent.press(screen.getByRole("button", { name: "7011 0000 руу залгах" }));
    expect(openURL).toHaveBeenCalledWith("tel:70110000");
  });
});

test("after an admin reset the notice is the only screen until acknowledged", async () => {
  mockStore.set("lt.refresh", "r0");
  route({ "/api/v1/auth/refresh": () => err(401, "auth.admin_reset") });
  await app("/");
  expect(await screen.findByText("Системийн төлөв")).toBeOnTheScreen(); // signed in from storage
  // The next authenticated request refreshes and learns about the reset.
  await act(() => refreshSession());
  expect(await screen.findByText("Таны нууц үгийг админ шинэчилсэн байна")).toBeOnTheScreen();
  expect(screen.getByText(/7011 0000 руу нэн даруй залгана уу/)).toBeOnTheScreen();
  expect(mockStore.has("lt.refresh")).toBe(false);
  expect(AccessibilityInfo.announceForAccessibility).toHaveBeenCalledWith(
    expect.stringMatching(/нэн даруй залгана уу/),
  );

  await fireEvent.press(screen.getByRole("button", { name: "Шинэ нууц үгээр нэвтрэх" }));
  expect(await screen.findByLabelText("Хэрэглэгчийн нэр")).toBeOnTheScreen();
  expect(screen).toHavePathname("/login");
  expect(mockStore.has("lt.admin_reset")).toBe(false);
});

test("the admin-reset notice survives an app restart until acknowledged", async () => {
  mockStore.set("lt.admin_reset", "1");
  await app("/");
  expect(await screen.findByText("Таны нууц үгийг админ шинэчилсэн байна")).toBeOnTheScreen();
  expect(screen).toHavePathname("/admin-reset");
});

test("camera denied: settings button and the SMS-link alternative", async () => {
  mockCamera.permission = { granted: false, canAskAgain: false };
  await app("/activate");
  expect(await screen.findByRole("button", { name: "Тохиргоог нээх" })).toBeOnTheScreen();
  expect(screen.getByText(/SMS-ээр авч/)).toBeOnTheScreen();
});
