import { defineConfig, devices } from "@playwright/test";

/**
 * E2E intentionally exercises the built application. Fixture mode is explicit so
 * these checks never contact a live election API or depend on network data.
 */
export default defineConfig({
  testDir: "./e2e",
  testIgnore: "normalized-public.spec.ts",
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 2 : 0,
  reporter: process.env.CI ? [["html", { open: "never" }], ["list"]] : "list",
  use: {
    baseURL: process.env.PLAYWRIGHT_BASE_URL ?? "http://127.0.0.1:3100",
    trace: "on-first-retry",
    screenshot: "only-on-failure",
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
  webServer: process.env.PLAYWRIGHT_BASE_URL
    ? undefined
    : {
        command:
          "pnpm build && NEXT_PUBLIC_SYNTHETIC_FIXTURE=true pnpm start --port 3100",
        url: "http://127.0.0.1:3100/es",
        timeout: 180_000,
        reuseExistingServer: !process.env.CI,
      },
});
