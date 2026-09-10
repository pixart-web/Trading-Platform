import { defineConfig, devices } from "@playwright/test";

export default defineConfig({
  testDir: "./e2e",
  fullyParallel: true,
  retries: 0,
  use: { baseURL: "http://127.0.0.1:3000", trace: "retain-on-failure" },
  projects: [{ name: "chromium", use: {
    ...devices["Desktop Chrome"], channel: process.env.PA_TEST_BROWSER_CHANNEL,
  } }],
  webServer: {
    command: "node node_modules/next/dist/bin/next start --hostname 127.0.0.1",
    url: "http://127.0.0.1:3000", reuseExistingServer: !process.env.CI, timeout: 60000,
  },
});
