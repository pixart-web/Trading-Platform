import { defineConfig, devices } from "@playwright/test";
import { createHash, randomBytes } from "node:crypto";
import { mkdtempSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

// Disposable test credentials; production authentication remains enabled.
const secrets = mkdtempSync(join(tmpdir(), "pocket-alpha-web-e2e-"));
const pinFile = join(secrets, "pin-hash");
const sessionFile = join(secrets, "session-secret");
writeFileSync(pinFile, createHash("sha256").update("908172").digest("hex"), { mode: 0o600 });
writeFileSync(sessionFile, randomBytes(48).toString("hex"), { mode: 0o600 });

export default defineConfig({
  testDir: "./e2e",
  fullyParallel: true,
  retries: 0,
  use: { baseURL: "http://localhost:3000", trace: "retain-on-failure" },
  projects: [{ name: "chromium", use: {
    ...devices["Desktop Chrome"], channel: process.env.PA_TEST_BROWSER_CHANNEL,
  } }],
  webServer: {
    command: "node node_modules/next/dist/bin/next start --hostname 127.0.0.1",
    url: "http://localhost:3000",
    reuseExistingServer: process.env.PA_REUSE_SERVER === "1",
    env: {
      PA_OPERATOR_ID: "operator",
      PA_OPERATOR_PIN_HASH_FILE: pinFile,
      PA_SESSION_SECRET_FILE: sessionFile,
    },
    timeout: 60000,
  },
});
