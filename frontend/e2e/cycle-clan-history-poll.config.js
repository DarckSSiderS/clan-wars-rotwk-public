import { defineConfig } from '@playwright/test';
import { fileURLToPath } from 'node:url';
import base from '../playwright.config.js';

export default defineConfig({
  ...base,
  testDir: '.', testMatch: 'cycle-clan-history-poll.spec.js',
  outputDir: '../test-results/clan-history-poll',
  use: { ...base.use, baseURL: 'http://127.0.0.1:4197' },
  webServer: { ...base.webServer,
    cwd: fileURLToPath(new URL('..', import.meta.url)),
    command: `node --input-type=module -e "import { createServer } from 'vite'; const server = await createServer({ server: { host: '127.0.0.1', port: 4197, strictPort: true, watch: { ignored: ['**/.tmp/**'] } } }); await server.listen();"`,
    url: 'http://127.0.0.1:4197', reuseExistingServer: true,
  },
});
