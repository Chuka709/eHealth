import { configure } from "@testing-library/react-native";

// Router screens render cold in the first test of a file and the suites run in parallel:
// the 1 s default for findBy* made tests flaky under load, not wrong.
configure({ asyncUtilTimeout: 5000 });
// The whole-flow tests (consents onboarding, language switch) await several screens in a row; with
// the per-test limit at Jest's 5 s default, one slow findBy used it all up (1.12: the flakiness).
jest.setTimeout(20_000);

// Native modules added in Phase 2.3. MMKV (a Nitro module) needs the native binary: an in-memory
// stand-in, one map per store id (a new id is a new, empty store - as on the device).
jest.mock("react-native-mmkv", () => {
  const stores = new Map<string, Map<string, string | number | boolean>>();
  return {
    createMMKV: ({ id = "mmkv.default" }: { id?: string } = {}) => {
      const data = stores.get(id) ?? new Map<string, string | number | boolean>();
      stores.set(id, data);
      const typed = <T>(key: string, type: string) => {
        const value = data.get(key);
        return typeof value === type ? (value as T) : undefined;
      };
      return {
        set: (key: string, value: string | number | boolean) => {
          data.set(key, value);
        },
        getString: (key: string) => typed<string>(key, "string"),
        getNumber: (key: string) => typed<number>(key, "number"),
        getBoolean: (key: string) => typed<boolean>(key, "boolean"),
        contains: (key: string) => data.has(key),
        remove: (key: string) => data.delete(key),
        getAllKeys: () => [...data.keys()],
        clearAll: () => data.clear(),
      };
    },
  };
});
jest.mock("@react-native-community/netinfo", () =>
  require("@react-native-community/netinfo/jest/netinfo-mock.js"),
);
jest.mock("expo-crypto", () => {
  const { randomUUID, randomBytes } =
    jest.requireActual<typeof import("node:crypto")>("node:crypto");
  return {
    randomUUID: () => randomUUID(),
    getRandomBytes: (n: number) => new Uint8Array(randomBytes(n)),
  };
});
jest.mock("expo-notifications", () => ({
  cancelAllScheduledNotificationsAsync: jest.fn(async () => undefined),
  dismissAllNotificationsAsync: jest.fn(async () => undefined),
  setNotificationHandler: jest.fn(),
}));
