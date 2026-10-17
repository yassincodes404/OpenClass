import { defineConfig, devices } from "@playwright/test";

const port = 17530;
const baseURL = `http://127.0.0.1:${port}`;

export default defineConfig({
  testDir: "./tests/portal",
  testMatch: "**/*.spec.ts",
  outputDir: "./test-results/portal",
  fullyParallel: false,
  workers: 1,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 1 : 0,
  timeout: 60_000,
  expect: { timeout: 10_000 },
  reporter: "list",
  use: {
    baseURL,
    browserName: "chromium",
    locale: "en-US",
    timezoneId: "UTC",
    reducedMotion: "no-preference",
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
    video: process.env.PORTAL_VIDEO ? "on" : "off",
    launchOptions: process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH
      ? { executablePath: process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH }
      : {},
  },
  projects: [
    {
      name: "desktop",
      use: {
        ...devices["Desktop Chrome"],
        viewport: { width: 1440, height: 900 },
        screen: { width: 1440, height: 900 },
        deviceScaleFactor: 1,
      },
    },
    {
      name: "mobile",
      use: {
        ...devices["Pixel 7"],
        viewport: { width: 390, height: 844 },
        screen: { width: 390, height: 844 },
        deviceScaleFactor: 1,
      },
    },
  ],
  webServer: {
    command: `pnpm --filter @openclass/portal exec vite --host 127.0.0.1 --port ${port} --strictPort`,
    url: baseURL,
    reuseExistingServer: false,
    timeout: 120_000,
  },
});
