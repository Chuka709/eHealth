import { describe, expect, it } from "vitest";

import { doseText } from "./dose";

const t = (key: string) =>
  ({ "units.mg": "мг", prnHint: "Хэрэгтэй үед", noDose: "Тун бүртгээгүй", "weekday.1": "Да" })[
    key
  ] ?? key;

describe("doseText", () => {
  it("writes each time with its amount, as entered", () => {
    expect(
      doseText(t, {
        dose_unit: "mg",
        schedule: {
          type: "daily",
          times: [
            { at: "08:00", amount: "2" },
            { at: "20:00", amount: "1.5" },
          ],
        },
      }),
    ).toBe("08:00 · 2 мг, 20:00 · 1.5 мг");
  });
  it("weekly with its days, as needed with its amount, nothing when nothing is known", () => {
    expect(
      doseText(t, {
        dose_unit: "mg",
        schedule: { type: "weekly", days: [1], times: [{ at: "09:00", amount: "5" }] },
      }),
    ).toBe("Да: 09:00 · 5 мг");
    expect(doseText(t, { dose_unit: "mg", dose_amount: "1", schedule: { type: "prn" } })).toBe(
      "Хэрэгтэй үед · 1 мг",
    );
    expect(doseText(t, {})).toBe("Тун бүртгээгүй");
  });
});
