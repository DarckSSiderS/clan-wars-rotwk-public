import { strict as assert } from 'node:assert';
import { test } from 'node:test';
import { fileURLToPath } from 'node:url';
import { ESLint } from 'eslint';
import { execFileSync } from 'node:child_process';

const cwd = fileURLToPath(new URL('../../', import.meta.url));

test('линтер исключает сборки, но продолжает проверять исходники', async () => {
  const eslint = new ESLint({ cwd });
  assert.equal(await eslint.isPathIgnored('dist/assets/chunk.js'), true);
  assert.equal(await eslint.isPathIgnored('dist-audit-local/assets/chunk.js'), true);
  assert.equal(await eslint.isPathIgnored('src/pages/CycleBattlesPage.jsx'), false);
});

test('сборка локального предпросмотра не попадает в Git', () => {
  const ignored = execFileSync('git', ['check-ignore', '--no-index', '--', 'dist-audit-local/index.html'],
    { cwd, encoding: 'utf8' });
  assert.equal(ignored.trim(), 'dist-audit-local/index.html');
});
