import { defineConfig, devices } from "@playwright/test";

// End-to-end tests run against a running stack (Docker infra, backend on :8000, `npm run start`).
// They create their own organization with synthetic example.com data.
export default defineConfig({
  testDir: "./e2e",
  timeout: 180_000, // one long journey test on a low-RAM machine
  expect: { timeout: 10_000 },
  fullyParallel: false,
  retries: 0,
  reporter: [["list"]],
  use: {
    baseURL: process.env.E2E_BASE_URL ?? "http://localhost:3000",
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
});
