import { apiBaseUrl } from "@/lib/api-base";
import { queryClient } from "@/lib/query-client";

import { apiPath, createAuthFetch } from "./auth-fetch";
import { establishSession, refreshSession, restoreSession, signOut, wipeLocal } from "./session";
import { clearAccessToken, getAccessToken, getStatus, setStatus } from "./session-store";

const mockStore = new Map<string, string>();
const mockOptions: unknown[] = [];

const mockInstall = { marker: true, failRead: false };

jest.mock("expo-file-system", () => ({
  Paths: { document: "doc" },
  File: class {
    get exists() {
      return mockInstall.marker;
    }
    create() {
      mockInstall.marker = true;
    }
    async write() {}
  },
}));

jest.mock("expo-secure-store", () => ({
  WHEN_UNLOCKED_THIS_DEVICE_ONLY: 6,
  getItemAsync: jest.fn(async (key: string, options: unknown) => {
    mockOptions.push(options);
    if (mockInstall.failRead) throw new Error("User interaction is not allowed.");
    return mockStore.get(key) ?? null;
  }),
  setItemAsync: jest.fn(async (key: string, value: string, options: unknown) => {
    mockOptions.push(options);
    mockStore.set(key, value);
  }),
  deleteItemAsync: jest.fn(async (key: string, options: unknown) => {
    mockOptions.push(options);
    mockStore.delete(key);
  }),
}));

type Handler = (request: Request) => Promise<Response> | Response;
const mockFetch = jest.fn<Promise<Response>, [Request]>();
const calls = (path: string) =>
  mockFetch.mock.calls.filter(([request]) => request.url === `${apiBaseUrl}${path}`);

function route(handlers: Record<string, Handler>) {
  mockFetch.mockImplementation(async (input: Request | string, init?: RequestInit) => {
    const request = typeof input === "string" ? new Request(input, init) : input;
    const handler = handlers[request.url.slice(apiBaseUrl.length)];
    if (!handler) throw new Error(`unexpected ${request.url}`);
    return handler(request);
  });
}

const json = (status: number, body: unknown) =>
  new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
const tokens = (n: number) =>
  json(200, {
    access_token: `access-${n}`,
    token_type: "bearer",
    expires_in: 900,
    refresh_token: `refresh-${n}`,
  });
const expired = () =>
  json(401, { code: "auth.session_invalid", message_key: "error.auth.session_invalid" });

beforeEach(() => {
  mockStore.clear();
  mockOptions.length = 0;
  mockInstall.marker = true;
  mockInstall.failRead = false;
  mockFetch.mockReset();
  globalThis.fetch = mockFetch as unknown as typeof fetch;
  clearAccessToken();
  setStatus("loading");
});

test("tokens are stored only with WHEN_UNLOCKED_THIS_DEVICE_ONLY", async () => {
  await establishSession({
    access_token: "a",
    token_type: "bearer",
    expires_in: 900,
    refresh_token: "r",
    device_token: "d",
  });
  expect(mockStore.get("lt.refresh")).toBe("r");
  expect(mockStore.get("lt.device")).toBe("d");
  expect(mockOptions.length).toBeGreaterThan(0);
  for (const options of mockOptions) expect(options).toEqual({ keychainAccessible: 6 });
  expect(getStatus()).toBe("signedIn");
});

test("restore without network: signed in only if a refresh token is stored", async () => {
  await restoreSession();
  expect(getStatus()).toBe("signedOut");
  mockStore.set("lt.refresh", "r0");
  await restoreSession();
  expect(getStatus()).toBe("signedIn");
  expect(mockFetch).not.toHaveBeenCalled();
});

test("a fresh install drops Keychain items left by a previous install", async () => {
  mockInstall.marker = false;
  mockStore.set("lt.refresh", "old");
  mockStore.set("lt.device", "old");
  await restoreSession();
  expect(getStatus()).toBe("signedOut");
  expect(mockStore.size).toBe(0);
  expect(mockInstall.marker).toBe(true);
});

test("an unreadable Keychain (locked phone) does not delete the session", async () => {
  mockStore.set("lt.refresh", "r0");
  mockInstall.failRead = true;
  await restoreSession();
  expect(getStatus()).toBe("signedOut");
  expect(await refreshSession()).toBe("offline");
  expect(mockStore.get("lt.refresh")).toBe("r0");
});

test("sign-out during a refresh is not undone by the refresh response", async () => {
  mockStore.set("lt.refresh", "r0");
  setStatus("signedIn");
  let release: () => void = () => undefined;
  const gate = new Promise<void>((resolve) => {
    release = resolve;
  });
  const revoked: unknown[] = [];
  route({
    "/api/v1/auth/refresh": async () => {
      await gate;
      return tokens(1);
    },
    "/api/v1/auth/logout": async (request) => {
      revoked.push(await request.json());
      return new Response(null, { status: 204 });
    },
  });
  const refreshing = refreshSession();
  const signingOut = signOut();
  release();
  await Promise.all([refreshing, signingOut]);
  // The newest token is revoked, and nothing is written back after the wipe.
  expect(revoked).toEqual([{ refresh_token: "refresh-1" }]);
  expect(mockStore.has("lt.refresh")).toBe(false);
  expect(getAccessToken()).toBeNull();
  expect(getStatus()).toBe("signedOut");
});

test("a refresh racing a wipe does not write its token back", async () => {
  mockStore.set("lt.refresh", "r0");
  let release: () => void = () => undefined;
  const gate = new Promise<void>((resolve) => {
    release = resolve;
  });
  route({
    "/api/v1/auth/refresh": async () => {
      await gate;
      return tokens(1);
    },
  });
  const refreshing = refreshSession();
  await wipeLocal("signedOut");
  release();
  expect(await refreshing).toBe("signedOut");
  expect(mockStore.has("lt.refresh")).toBe(false);
  expect(getAccessToken()).toBeNull();
});

test("the admin-reset notice is not replaced by later signed-out refreshes", async () => {
  mockStore.set("lt.refresh", "r0");
  mockStore.set("lt.device", "d0");
  route({
    "/api/v1/auth/refresh": () =>
      json(401, { code: "auth.admin_reset", message_key: "error.auth.admin_reset" }),
  });
  expect(await refreshSession()).toBe("notice");
  // The server dropped the device trust too.
  expect(mockStore.has("lt.device")).toBe(false);
  expect(await refreshSession()).toBe("signedOut");
  await wipeLocal("signedOut");
  expect(getStatus()).toBe("notice");
});

test("concurrent refreshes share one rotation (single-flight)", async () => {
  mockStore.set("lt.refresh", "r0");
  let release: () => void = () => undefined;
  const gate = new Promise<void>((resolve) => {
    release = resolve;
  });
  route({
    "/api/v1/auth/refresh": async () => {
      await gate;
      return tokens(1);
    },
  });

  const all = Promise.all([refreshSession(), refreshSession(), refreshSession()]);
  release();
  expect(await all).toEqual(["ok", "ok", "ok"]);
  expect(calls("/api/v1/auth/refresh")).toHaveLength(1);
  expect(mockStore.get("lt.refresh")).toBe("refresh-1");
  expect(getAccessToken()).toBe("access-1");

  // The next refresh is a new flight with the rotated token.
  route({
    "/api/v1/auth/refresh": async (request) => {
      expect(await request.json()).toEqual({ refresh_token: "refresh-1" });
      return tokens(2);
    },
  });
  expect(await refreshSession()).toBe("ok");
});

test("admin_reset wipes credentials and cache and the trusted-device token", async () => {
  mockStore.set("lt.refresh", "r0");
  mockStore.set("lt.device", "d0");
  queryClient.setQueryData(["me"], { display_name: "x" });
  setStatus("signedIn");
  route({
    "/api/v1/auth/refresh": () =>
      json(401, { code: "auth.admin_reset", message_key: "error.auth.admin_reset" }),
  });

  expect(await refreshSession()).toBe("notice");
  expect(getStatus()).toBe("notice");
  expect(mockStore.has("lt.refresh")).toBe(false);
  expect(mockStore.has("lt.device")).toBe(false);
  expect(queryClient.getQueryData(["me"])).toBeUndefined();
});

test("a network error or 5xx keeps the session (offline)", async () => {
  mockStore.set("lt.refresh", "r0");
  setStatus("signedIn");
  mockFetch.mockRejectedValueOnce(new TypeError("Network request failed"));
  expect(await refreshSession()).toBe("offline");
  route({ "/api/v1/auth/refresh": () => json(503, { code: "internal", message_key: "x" }) });
  expect(await refreshSession()).toBe("offline");
  expect(mockStore.get("lt.refresh")).toBe("r0");
  expect(getStatus()).toBe("signedIn");
});

test("sign-out revokes on the server and wipes even when offline", async () => {
  mockStore.set("lt.refresh", "r0");
  mockStore.set("lt.device", "d0");
  setStatus("signedIn");
  mockFetch.mockRejectedValueOnce(new TypeError("Network request failed"));
  await signOut();
  expect(calls("/api/v1/auth/logout")).toHaveLength(1);
  expect(mockStore.has("lt.refresh")).toBe(false);
  expect(mockStore.get("lt.device")).toBe("d0");
  expect(getStatus()).toBe("signedOut");
});

describe("auth fetch", () => {
  const authFetch = createAuthFetch(apiBaseUrl);
  const auth = (request: Request | undefined) => request?.headers.get("Authorization");

  test("adds the bearer only for our API and never for anonymous endpoints", async () => {
    mockStore.set("lt.refresh", "r0");
    route({ "/api/v1/auth/refresh": () => tokens(1), "/api/v1/me": () => json(200, {}) });
    await authFetch(`${apiBaseUrl}/api/v1/me`);
    expect(auth(calls("/api/v1/me")[0]?.[0])).toBe("Bearer access-1");

    mockFetch.mockClear();
    route({ "/api/v1/auth/login": () => json(200, {}) });
    await authFetch(`${apiBaseUrl}/api/v1/auth/login`, { method: "POST" });
    expect(auth(calls("/api/v1/auth/login")[0]?.[0])).toBeNull();

    mockFetch.mockResolvedValueOnce(json(200, {}));
    await authFetch("https://evil.example/api/v1/me");
    expect(auth(mockFetch.mock.calls.at(-1)?.[0])).toBeNull();
  });

  test("a 401 refreshes once and retries the request with its body", async () => {
    mockStore.set("lt.refresh", "r0");
    let n = 0;
    route({
      "/api/v1/auth/refresh": () => tokens(++n),
      "/api/v1/me": async (request) => {
        expect(await request.json()).toEqual({ display_name: "Б" });
        return auth(request) === "Bearer access-1" ? expired() : json(200, { ok: true });
      },
    });
    const response = await authFetch(`${apiBaseUrl}/api/v1/me`, {
      method: "PATCH",
      body: JSON.stringify({ display_name: "Б" }),
      headers: { "Content-Type": "application/json" },
    });
    expect(response.status).toBe(200);
    expect(calls("/api/v1/auth/refresh")).toHaveLength(2);
    expect(calls("/api/v1/me")).toHaveLength(2);
  });

  test("parallel 401s trigger a single refresh", async () => {
    mockStore.set("lt.refresh", "r0");
    route({ "/api/v1/auth/refresh": () => tokens(1), "/api/v1/me": () => json(200, {}) });
    await refreshSession(); // access-1 in memory
    mockFetch.mockClear();
    let n = 1;
    route({
      "/api/v1/auth/refresh": () => tokens(++n),
      "/api/v1/me": (request) => (auth(request) === "Bearer access-1" ? expired() : json(200, {})),
    });
    const responses = await Promise.all([1, 2, 3].map(() => authFetch(`${apiBaseUrl}/api/v1/me`)));
    expect(responses.map((r) => r.status)).toEqual([200, 200, 200]);
    expect(calls("/api/v1/auth/refresh")).toHaveLength(1);
  });

  test("a rejected fresh token signs out", async () => {
    mockStore.set("lt.refresh", "r0");
    setStatus("signedIn");
    let n = 0;
    route({ "/api/v1/auth/refresh": () => tokens(++n), "/api/v1/me": () => expired() });
    const response = await authFetch(`${apiBaseUrl}/api/v1/me`);
    expect(response.status).toBe(401);
    expect(getStatus()).toBe("signedOut");
    expect(mockStore.has("lt.refresh")).toBe(false);
  });

  test("offline without a valid token surfaces a network error", async () => {
    mockStore.set("lt.refresh", "r0");
    mockFetch.mockRejectedValue(new TypeError("Network request failed"));
    await expect(authFetch(`${apiBaseUrl}/api/v1/me`)).rejects.toThrow("Network request failed");
  });
});

test("apiPath matches only our origin, not look-alike hosts", () => {
  expect(apiPath(`${apiBaseUrl}/api/v1/me?x=1`, apiBaseUrl)).toBe("/api/v1/me");
  expect(apiPath(`${apiBaseUrl}.evil.example/api/v1/me`, apiBaseUrl)).toBeNull();
  expect(apiPath("https://evil.example/api", apiBaseUrl)).toBeNull();
});

test("a wrong current password (401 invalid_credentials) is not refreshed, replayed or wiped", async () => {
  mockStore.set("lt.refresh", "r0");
  setStatus("signedIn");
  route({
    "/api/v1/auth/refresh": () => tokens(1),
    "/api/v1/auth/password": () =>
      json(401, {
        code: "auth.invalid_credentials",
        message_key: "error.auth.invalid_credentials",
      }),
  });
  const authFetch = createAuthFetch(apiBaseUrl);
  const response = await authFetch(`${apiBaseUrl}/api/v1/auth/password`, { method: "POST" });
  expect(response.status).toBe(401);
  expect(calls("/api/v1/auth/password")).toHaveLength(1);
  expect(calls("/api/v1/auth/refresh")).toHaveLength(1); // only the initial token fetch
  expect(getStatus()).toBe("signedIn");
  expect(mockStore.get("lt.refresh")).toBe("refresh-1");
});

test("a redirect is never followed with the token", async () => {
  mockStore.set("lt.refresh", "r0");
  route({
    "/api/v1/auth/refresh": () => tokens(1),
    "/api/v1/me": () => {
      const response = json(200, {});
      Object.defineProperty(response, "redirected", { value: true });
      return response;
    },
  });
  const authFetch = createAuthFetch(apiBaseUrl);
  await expect(authFetch(`${apiBaseUrl}/api/v1/me`)).rejects.toThrow("Network request failed");
});

test.each([
  ["@evil.example/api/v1/me"],
  [String.raw`\@evil.example/api/v1/me`],
  [".evil.example/api/v1/me"],
  [":443/api/v1/me"],
])("apiPath rejects %s appended to the base URL", (suffix) => {
  const path = apiPath(`${apiBaseUrl}${suffix}`, apiBaseUrl);
  expect(path).toBeNull();
});

test("apiPath ignores a trailing slash, so public endpoints stay anonymous", () => {
  expect(apiPath(`${apiBaseUrl}/api/v1/auth/login/`, apiBaseUrl)).toBe("/api/v1/auth/login");
  expect(apiPath(`${apiBaseUrl.toUpperCase()}/api/v1/me`, apiBaseUrl)).toBeNull();
});
