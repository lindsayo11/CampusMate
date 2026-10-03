import { defineConfig, devices } from '@playwright/test';
export default defineConfig({
  testDir: './e2e', fullyParallel: false, workers: 1,
  use: { baseURL: process.env.E2E_BASE_URL || 'http://127.0.0.1:3000', trace: 'retain-on-failure',
    launchOptions: process.env.CHROMIUM_PATH ? { executablePath: process.env.CHROMIUM_PATH, args: ['--no-sandbox', '--disable-dev-shm-usage', '--disable-gpu'] } : {} },
  projects: [ { name: 'desktop', use: { ...devices['Desktop Chrome'] } },
              { name: 'mobile', use: { ...devices['Pixel 7'] } } ],
});
