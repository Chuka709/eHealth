import { Linking } from "react-native";

jest.mock("expo-constants", () => ({
  __esModule: true,
  default: { expoConfig: { android: { package: "mn.munkhly.labtrack.development" } } },
}));

import { openLockScreenPermission } from "./use-reminder-health";

afterEach(() => jest.restoreAllMocks());

test("Xiaomi: opens the app's own MIUI permissions page (Show on Lock screen)", async () => {
  const sendIntent = jest.spyOn(Linking, "sendIntent").mockResolvedValue(undefined);
  await openLockScreenPermission();
  expect(sendIntent).toHaveBeenCalledWith("miui.intent.action.APP_PERM_EDITOR", [
    { key: "extra_pkgname", value: "mn.munkhly.labtrack.development" },
  ]);
});

test("not MIUI (no such page): the app's own settings instead", async () => {
  jest.spyOn(Linking, "sendIntent").mockRejectedValue(new Error("no activity"));
  const openSettings = jest.spyOn(Linking, "openSettings").mockResolvedValue(undefined);
  await openLockScreenPermission();
  expect(openSettings).toHaveBeenCalled();
});
