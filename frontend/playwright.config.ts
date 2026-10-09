import { defineConfig, devices } from '@playwright/test';

/**
 * Browser E2E tests against a production build of the frontend and a
 * deterministic stub backend (e2e/stub-server.mjs). No real API, database,
 * GAF, Perplexity or OpenAI access. Tests share the stub's state, so they run serially.
 */
const APP_PORT = 3100;
const STUB_PORT = 8765;

export default defineConfig({
  testDir: './e2e',
  fullyParallel: false,
  workers: 1,
  retries: process.env.CI ? 1 : 0,
  timeout: 60_000,
  expect: { timeout: 15_000 },
  reporter: process.env.CI ? [['list'], ['html', { open: 'never' }]] : 'list',
  use: {
    baseURL: `http://127.0.0.1:${APP_PORT}`,
    trace: 'retain-on-failure',
  },
  projects: [{ name: 'chromium', use: { ...devices['Desktop Chrome'] } }],
  webServer: [
    {
      command: 'node e2e/stub-server.mjs',
      url: `http://127.0.0.1:${STUB_PORT}/health`,
      reuseExistingServer: false,
      env: { STUB_PORT: String(STUB_PORT) },
    },
    {
      command: 'node e2e/serve-app.mjs',
      url: `http://127.0.0.1:${APP_PORT}`,
      reuseExistingServer: false,
      timeout: 300_000,
      env: { STUB_PORT: String(STUB_PORT), E2E_APP_PORT: String(APP_PORT) },
    },
  ],
});
