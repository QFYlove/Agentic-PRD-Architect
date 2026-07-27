import { defineConfig, devices } from "@playwright/test";

const manageWebServers = process.env.E2E_EXTERNAL_SERVERS !== "true";

export default defineConfig({
  testDir: "./e2e",
  fullyParallel: false,
  workers: 1,
  timeout: 30_000,
  expect: { timeout: 12_000 },
  reporter: "list",
  use: {
    baseURL: "http://127.0.0.1:4331",
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
    video: "retain-on-failure",
  },
  projects: [
    {
      name: "chromium",
      use: { ...devices["Desktop Chrome"] },
    },
  ],
  ...(manageWebServers
    ? {
        webServer: [
          {
            command:
              ".venv\\Scripts\\python.exe -m uvicorn backend.main:app " +
              "--host 127.0.0.1 --port 8011",
            env: {
              APP_ENV: "test",
              E2E_TEST_MODE: "true",
              ENABLE_MOCK_LLM: "true",
              DATABASE_PATH: ":memory:",
              FRONTEND_ORIGINS: "http://127.0.0.1:4331",
              GENERATOR_TIMEOUT_SECONDS: "1",
              RUN_TIMEOUT_SECONDS: "20",
              MOCK_GENERATOR_DELAY_SECONDS: "0.02",
              MOCK_REVIEWER_DELAY_SECONDS: "0.35",
              MOCK_OPTIMIZER_DELAY_SECONDS: "0.03",
            },
            url: "http://127.0.0.1:8011/api/health",
            reuseExistingServer: false,
            timeout: 120_000,
          },
          {
            command:
              "node node_modules\\astro\\astro.js dev --host 127.0.0.1 --port 4331",
            env: {
              ASTRO_TELEMETRY_DISABLED: "1",
              E2E_TEST_MODE: "true",
              PUBLIC_API_BASE_URL: "http://127.0.0.1:4331",
              API_PROXY_TARGET: "http://127.0.0.1:8011",
            },
            url: "http://127.0.0.1:4331",
            reuseExistingServer: false,
            timeout: 120_000,
          },
        ],
      }
    : {}),
});
