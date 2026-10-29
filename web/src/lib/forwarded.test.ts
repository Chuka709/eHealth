import { describe, expect, it } from "vitest";

import { forwardedClientIp } from "./forwarded";

describe("forwardedClientIp", () => {
  it("takes the address Caddy wrote (the last entry)", () => {
    expect(forwardedClientIp("203.0.113.7")).toBe("203.0.113.7");
    expect(forwardedClientIp("10.9.9.9, 198.51.100.4")).toBe("198.51.100.4");
    expect(forwardedClientIp("2001:db8::1")).toBe("2001:db8::1");
  });

  it("drops anything that is not an IP", () => {
    for (const value of [null, "", "unknown", "1.2.3.4, evil", "<script>", "1.2.3.4:80"]) {
      expect(forwardedClientIp(value)).toBeNull();
    }
  });
});
