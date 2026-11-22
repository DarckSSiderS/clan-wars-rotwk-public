import { defineConfig } from '@playwright/test';
import { fileURLToPath } from 'node:url';
import process from 'node:process';
import base from '../playwright.config.js';

const port = Number(process.env.SEASON_ARCHIVE_TEST_PORT || 4207);
export default defineConfig({
  ...base,
  testDir: '.',
  testMatch: 'season-archive.spec.js',
  outputDir: '../test-results/season-archive',
  use: { ...base.use, baseURL: `http://127.0.0.1:${port}`, locale: 'ru-RU', viewport: { width: 1600, height: 1000 } },
  webServer: process.env.SEASON_ARCHIVE_EXTERNAL_SERVER === 'true' ? undefined : { ...base.webServer,
    reuseExistingServer: process.env.SEASON_ARCHIVE_REUSE_SERVER === 'true',
    cwd: fileURLToPath(new URL('..', import.meta.url)),
    command: `node node_modules/vite/bin/vite.js --host 127.0.0.1 --port ${port} --strictPort`,
    url: `http://127.0.0.1:${port}`,
  },
});
