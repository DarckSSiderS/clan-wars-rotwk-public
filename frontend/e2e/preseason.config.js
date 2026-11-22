import { defineConfig } from '@playwright/test';
import base from '../playwright.config.js';
import { fileURLToPath } from 'node:url';
import process from 'node:process';

export default defineConfig({
  ...base, testDir: '.', testMatch: ['preseason.spec.js', 'cycle-preparation.spec.js'], outputDir: '../test-results/preseason',
  use: { ...base.use, baseURL: 'http://127.0.0.1:4233', locale: 'ru-RU' },
  webServer: process.env.PRESEASON_EXTERNAL_SERVER === 'true' ? undefined : { ...base.webServer, cwd: fileURLToPath(new URL('..', import.meta.url)),
    command: '"C:/Users/admin/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin/node.exe" node_modules/vite/bin/vite.js --host 127.0.0.1 --port 4233 --strictPort',
    url: 'http://127.0.0.1:4233', reuseExistingServer: false },
});
