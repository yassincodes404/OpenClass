import { defineConfig, devices } from "@playwright/test";
const live = process.env.OPENCLASS_LIVE_BACKEND === "1";
export default defineConfig({
  testDir: "./tests/web",
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 1 : 0,
  reporter: "list",
  use: {
    baseURL: "http://127.0.0.1:17330",
    trace: "retain-on-failure",
    launchOptions: process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH
      ? { executablePath: process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH }
      : {},
  },
  projects: [
    { name: "desktop", testIgnore: "**/live/**", use: { ...devices["Desktop Chrome"] } },
    { name: "mobile", testIgnore: "**/live/**", use: { ...devices["Pixel 7"] } },
    {
      name: "live-backend",
      testMatch: "**/live/**/*.spec.ts",
      fullyParallel: false,
      workers: 1,
      retries: 0,
      timeout: 120_000,
      use: {
        ...devices["Desktop Chrome"],
        baseURL: process.env.OPENCLASS_LIVE_BASE_URL,
        // Real authentication must not be saved in traces or storage-state files.
        trace: "off",
        screenshot: "only-on-failure",
      },
    },
  ],
  webServer: live
    ? undefined
    : {
        command: "pnpm --filter @openclass/web exec next dev --hostname 127.0.0.1 --port 17330",
        url: "http://127.0.0.1:17330",
        reuseExistingServer: false,
        env: { NEXT_TELEMETRY_DISABLED: "1" },
      },
});
