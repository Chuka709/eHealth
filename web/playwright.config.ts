import { defineConfig, devices } from "@playwright/test";

// Runs against the compose stack through Caddy (`just up`, then `just e2e-web`).
export default defineConfig({
  testDir: "./e2e",
  globalSetup: "./e2e/global-setup.ts",
  workers: 1, // one admin, one TOTP step per sign-in
  timeout: 120_000,
  expect: { timeout: 20_000 }, // argon2 + TOTP + DB per sign-in, dev images
  reporter: [["list"]],
  use: {
    baseURL: process.env.E2E_BASE_URL ?? "http://localhost:8080",
    locale: "mn-MN",
    trace: "off", // traces would capture the activation QR and session cookie
    screenshot: "off",
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
});
