import { parsePrivacyUrl } from "./support";

test("the privacy policy link is https only", () => {
  expect(parsePrivacyUrl(" https://example.mn/privacy ")).toBe("https://example.mn/privacy");
  expect(parsePrivacyUrl("http://example.mn/privacy")).toBeNull();
  expect(parsePrivacyUrl("javascript:alert(1)")).toBeNull();
  expect(parsePrivacyUrl("https://localhost")).toBeNull();
  expect(parsePrivacyUrl(undefined)).toBeNull();
});

test("a privacy link with credentials in it is refused", () => {
  expect(parsePrivacyUrl("https://evil.example@example.mn/privacy")).toBeNull();
});
