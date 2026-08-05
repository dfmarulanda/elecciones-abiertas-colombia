import { defineConfig, devices } from "@playwright/test";

const apiURL = "http://127.0.0.1:3210";

export default defineConfig({
  testDir: "./e2e",
  testMatch: "normalized-public.spec.ts",
  fullyParallel: false,
  forbidOnly: Boolean(process.env.CI),
  retries: process.env.CI ? 2 : 0,
  reporter: process.env.CI ? [["html", { open: "never" }], ["list"]] : "list",
  use: {
    baseURL: "http://127.0.0.1:3102",
    trace: "on-first-retry",
    screenshot: "only-on-failure",
  },
  projects: [
    { name: "normalized-chromium", use: { ...devices["Desktop Chrome"] } },
  ],
  webServer: [
    {
      command: "node e2e/normalized-api-server.mjs",
      url: `${apiURL}/healthz`,
      timeout: 30_000,
      reuseExistingServer: !process.env.CI,
    },
    {
      command: `NEXT_PUBLIC_API_URL=${apiURL} pnpm build && NEXT_PUBLIC_API_URL=${apiURL} pnpm start --port 3102`,
      url: "http://127.0.0.1:3102/es/resultados",
      timeout: 180_000,
      reuseExistingServer: !process.env.CI,
    },
  ],
});
