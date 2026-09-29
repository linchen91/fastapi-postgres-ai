import { defineConfig, devices } from '@playwright/test';

const baseURL =
  process.env.AZURE_BASE_URL ||
  'https://ca-fastapi-ai.jollywave-3dee1d3c.germanywestcentral.azurecontainerapps.io';

export default defineConfig({
  testDir: './tests',
  testMatch: '**/azure-live.spec.js',
  fullyParallel: false,
  forbidOnly: !!process.env.CI,
  retries: 1,
  reporter: [['list'], ['html', { open: 'never' }]],
  timeout: 90_000,
  expect: { timeout: 30_000 },
  use: {
    baseURL,
    trace: 'on-first-retry',
    navigationTimeout: 60_000,
    actionTimeout: 30_000,
  },
  projects: [
    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'] },
    },
  ],
});
