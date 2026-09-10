import { defineConfig, devices } from '@playwright/test'

/**
 * E2E configuration for the Cowork backbone.
 *
 * Default: boots the FastAPI backend in-process test mode (sqlite, in-memory event bus, MockRuntime, inline
 * jobs) on :8000 and the Vite dev server (proxying /v1 to :8000) on :5173, then drives the SPA with Chromium.
 *
 * Against an already running stack (e.g. `docker compose up`): set E2E_BASE_URL=http://localhost:5173 and no
 * servers are started (see README.md).
 */
const externalBaseUrl = process.env.E2E_BASE_URL
const baseURL = externalBaseUrl || 'http://localhost:5173'
// Chromium is pre-installed under PLAYWRIGHT_BROWSERS_PATH (revision 1194 == @playwright/test 1.56).
// E2E_CHROMIUM_PATH can point at the binary explicitly if the registry lookup ever fails.
const executablePath = process.env.E2E_CHROMIUM_PATH || undefined

export default defineConfig({
  testDir: './specs',
  timeout: 90_000,
  expect: { timeout: 15_000 },
  // All specs share one backend and the same seeded users; keep them serial so a pending approval or a
  // capability kill-switch toggled in one spec cannot interfere with another.
  fullyParallel: false,
  workers: 1,
  retries: 1,
  reporter: [['list'], ['html', { outputFolder: 'report', open: 'never' }]],
  outputDir: 'test-results',
  use: {
    baseURL,
    headless: true,
    trace: 'on-first-retry',
    screenshot: 'only-on-failure',
    ...(executablePath ? { launchOptions: { executablePath } } : {}),
  },
  projects: [{ name: 'chromium', use: { ...devices['Desktop Chrome'] } }],
  webServer: externalBaseUrl
    ? undefined
    : [
        {
          // Recreates + seeds the sqlite DB, then runs uvicorn on :8000 (see scripts/start-backend.sh).
          command: 'bash scripts/start-backend.sh',
          url: 'http://localhost:8000/healthz',
          reuseExistingServer: true,
          timeout: 120_000,
          stdout: 'ignore',
          stderr: 'pipe',
        },
        {
          command: 'npm run dev -- --port 5173 --strictPort',
          cwd: '../../frontend',
          url: 'http://localhost:5173',
          reuseExistingServer: true,
          timeout: 120_000,
          stdout: 'ignore',
          stderr: 'pipe',
        },
      ],
})
