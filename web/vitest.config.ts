import { defineConfig } from "vitest/config";

// Unit tests only: e2e/*.spec.ts are Playwright tests (`just e2e-web`) and fail under Vitest.
export default defineConfig({
  test: { include: ["src/**/*.test.{ts,tsx}"] },
});
