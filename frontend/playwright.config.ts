import { defineConfig } from "@playwright/test";

export default defineConfig({
  testDir: "e2e",
  timeout: 60_000,
  workers: 1,
  use: {
    baseURL: "http://localhost:8100",
    launchOptions: { executablePath: process.env.CHROMIUM_PATH ?? "/opt/pw-browsers/chromium" },
    timezoneId: "Asia/Kolkata",
  },
  // Run `npm run build` first: the API serves the static dashboard from frontend/out.
  webServer: { command: "bash e2e/start-server.sh", url: "http://localhost:8100/healthz", timeout: 120_000, reuseExistingServer: false },
});
