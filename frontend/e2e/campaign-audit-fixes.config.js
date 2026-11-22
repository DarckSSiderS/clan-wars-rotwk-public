import { defineConfig } from '@playwright/test';
import { fileURLToPath } from 'node:url';
import process from 'node:process';
import base from '../playwright.config.js';
const port = Number(process.env.CAMPAIGN_TEST_PORT || 4198);

export default defineConfig({
  ...base,
  testDir: '.',
  testMatch: ['cycle-admin-controls.spec.js', 'cycle-defence-template.spec.js', 'cycle-clan-history-poll.spec.js',
    'cycle-battles.spec.js', 'cycle-map.spec.js', 'cycle-planning.spec.js'],
  outputDir: '../test-results/campaign-audit-fixes',
  use: { ...base.use, baseURL: `http://127.0.0.1:${port}`, viewport: { width: 1440, height: 1000 } },
  webServer: { ...base.webServer,
    cwd: fileURLToPath(new URL('..', import.meta.url)),
    command: `node --input-type=module -e "import { createServer } from 'vite'; const server = await createServer({ server: { host: '127.0.0.1', port: ${port}, strictPort: true, watch: { ignored: ['**/.tmp/**'] } } }); await server.listen();"`,
    url: `http://127.0.0.1:${port}`,
  },
});
