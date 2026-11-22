import { defineConfig } from '@playwright/test';

const browserExecutable = globalThis.process?.env.PLAYWRIGHT_EXECUTABLE_PATH;

export default defineConfig({
  testDir: './e2e',
  // Each test has an isolated browser context; CI shards individual cases
  // across separate runners while keeping one worker per runner.
  fullyParallel: Boolean(globalThis.process?.env.CI),
  workers: 1,
  use: {
    baseURL: 'http://127.0.0.1:4173',
    trace: 'retain-on-failure',
    launchOptions: browserExecutable
      ? { executablePath: browserExecutable }
      : {},
  },
  webServer: {
    command: 'node node_modules/vite/bin/vite.js --host 127.0.0.1 --port 4173',
    url: 'http://127.0.0.1:4173',
    reuseExistingServer: false,
    env: {
      VITE_AGENTATION_ENABLED: 'false',
      VITE_REALTIME_ENABLED: 'false',
    },
  },
});
