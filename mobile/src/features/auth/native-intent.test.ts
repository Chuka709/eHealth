import { parseSupportPhone } from "@/lib/support";
import {
  parseActivationLink,
  takeActivationTokenFromUrl,
  takePendingActivationToken,
} from "./activation-link";

import { redirectSystemPath } from "./native-intent";
import { setStatus } from "./session-store";

const token = "A".repeat(20) + "b_-".repeat(8); // 44 url-safe chars

beforeEach(() => {
  takePendingActivationToken();
});

test.each([
  `labtrack://activate#${token}`,
  `labtrack:///activate#${token}`,
  `/activate#${token}`,
  `activate#${token}`,
])("moves the token out of %s and routes to /activate", (path) => {
  expect(redirectSystemPath({ path, initial: true })).toBe("/activate");
  expect(takePendingActivationToken()).toBe(token);
  expect(takePendingActivationToken()).toBeNull(); // taken once
});

test("a malformed token is dropped, never routed", () => {
  expect(redirectSystemPath({ path: "labtrack://activate#short", initial: false })).toBe(
    "/activate",
  );
  expect(takePendingActivationToken()).toBeNull();
  expect(redirectSystemPath({ path: `labtrack://activate#${token}<script>`, initial: false })).toBe(
    "/activate",
  );
  expect(takePendingActivationToken()).toBeNull();
});

test("every other link opens the app at the start, without params or fragments", () => {
  expect(redirectSystemPath({ path: "/login#secret", initial: false })).toBe("/");
  expect(redirectSystemPath({ path: "/login?activated=1", initial: false })).toBe("/");
  expect(redirectSystemPath({ path: "labtrack://home", initial: true })).toBe("/");
  expect(takePendingActivationToken()).toBeNull();
});

test("QR text must be exactly an activation link", () => {
  expect(parseActivationLink(`labtrack://activate#${token}`)).toBe(token);
  expect(parseActivationLink(` labtrack://activate#${token}\n`)).toBe(token);
  expect(parseActivationLink(`https://evil.example/activate#${token}`)).toBeNull();
  expect(parseActivationLink(`labtrack://activate?t=${token}`)).toBeNull();
  expect(parseActivationLink(token)).toBeNull();
});

test("the launch URL yields its token only once", () => {
  const url = `labtrack://activate#${token}`;
  expect(takeActivationTokenFromUrl(url)).toBe(token);
  expect(takeActivationTokenFromUrl(url)).toBeNull();
  expect(takeActivationTokenFromUrl(null)).toBeNull();
});

test("a link opened while signed in is not kept for later", () => {
  setStatus("signedIn");
  expect(redirectSystemPath({ path: `labtrack://activate#${token}`, initial: false })).toBe(
    "/activate",
  );
  setStatus("signedOut");
  expect(takePendingActivationToken()).toBeNull();
});

test("a pending token expires after two minutes", () => {
  jest.useFakeTimers();
  redirectSystemPath({ path: `labtrack://activate#${token}`, initial: true });
  jest.advanceTimersByTime(2 * 60_000 + 1);
  expect(takePendingActivationToken()).toBeNull();
  jest.useRealTimers();
});

test.each([
  ["7011 0000", "tel:70110000"],
  ["+976 (11) 32-1234", "tel:+97611321234"],
])("support phone %s dials %s", (raw, url) => {
  expect(parseSupportPhone(raw)?.url).toBe(url);
});

test.each(["0000", "", "call me", "+976 11 32 1234 5678 9"])(
  "support phone %p is rejected",
  (raw) => {
    expect(parseSupportPhone(raw)).toBeNull();
  },
);
