import mn from "@labtrack/shared/messages/mn.json";
import { render, screen } from "@testing-library/react-native";
import { IntlProvider } from "use-intl";

import { MedAlarmSwitch } from "./med-alarm-switch";

const mockStored = new Map<string, boolean | string>();
jest.mock("@/lib/local-store", () => ({
  localStore: async () => ({
    getBoolean: (k: string) => mockStored.get(k) as boolean | undefined,
    getString: (k: string) => mockStored.get(k) as string | undefined,
    set: (k: string, v: boolean | string) => mockStored.set(k, v),
  }),
}));
jest.mock("./reminder-bus", () => ({ requestReminderSync: () => undefined }));

const show = (category: string | null) =>
  render(
    <IntlProvider locale="mn" messages={mn}>
      <MedAlarmSwitch medication={{ id: "m1", category }} />
    </IntlProvider>,
  );

beforeEach(() => {
  mockStored.clear();
});

test("Q79-3: the switch says what it does (shown on Android only, by the medicine screen)", async () => {
  await show("immunosuppressant");
  // the native switch's value is not readable here: its logic is tested in notify.test.ts
  expect(screen.getByTestId("med-alarm")).toBeOnTheScreen();
  expect(
    screen.getByText(/Унтраавал энэ эмийн сануулга энгийн чанга мэдэгдлээр/),
  ).toBeOnTheScreen();
});
