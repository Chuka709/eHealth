import { describe, expect, test } from "vitest";

import { statusKey } from "./status";

describe("statusKey", () => {
  test("unreachable when the API did not answer", () => {
    expect(statusKey(null)).toBe("unreachable");
  });

  test("ok only when every dependency is up", () => {
    expect(statusKey({ status: "ok", database: true, queue: true })).toBe("ok");
  });

  test("degraded when any dependency is down", () => {
    expect(statusKey({ status: "degraded", database: false, queue: true })).toBe("degraded");
    expect(statusKey({ status: "degraded", database: true, queue: false })).toBe("degraded");
  });
});
