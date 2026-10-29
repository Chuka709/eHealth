import { describe, expect, it } from "vitest";

import { forwardedClientIp } from "./forwarded";

describe("forwardedClientIp", () => {
  it("accepts the single address Caddy wrote", () => {
    expect(forwardedClientIp("203.0.113.7")).toBe("203.0.113.7");
    expect(forwardedClientIp(" 2001:db8::1 ")).toBe("2001:db8::1");
  });

  it("drops anything that is not one IP", () => {
    for (const value of [null, "", "unknown", "1.2.3.4, 5.6.7.8", "<script>", "1.2.3.4:80"]) {
      expect(forwardedClientIp(value)).toBeNull();
    }
  });
});
