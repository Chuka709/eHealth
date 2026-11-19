import { describe, expect, it } from "vitest";

import { formatDate, formatPartial, minutesSeconds } from "./dates";

describe("dates", () => {
  it("formats in Ulaanbaatar time as yyyy.MM.dd HH:mm", () => {
    expect(formatDate("2026-03-14T20:05:00Z")).toBe("2026.03.15");
    expect(formatDate("2026-03-14T20:05:00Z", true)).toBe("2026.03.15 04:05");
  });

  it("formats countdowns as m:ss", () => {
    expect(minutesSeconds(900)).toBe("15:00");
    expect(minutesSeconds(61)).toBe("1:01");
    expect(minutesSeconds(-3)).toBe("0:00");
  });
});

describe("formatPartial", () => {
  it("shows only what is known of a month- or year-only date", () => {
    expect(formatPartial("2024-03-01", "month")).toBe("2024.03");
    expect(formatPartial("2024-01-01", "year")).toBe("2024");
    expect(formatPartial("2024-03-14", "day")).toBe("2024.03.14");
  });
});
