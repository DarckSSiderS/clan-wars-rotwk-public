import test from 'node:test';
import assert from 'node:assert/strict';
import { Buffer } from 'node:buffer';
import { fileURLToPath } from 'node:url';
import { build } from 'esbuild';
import { defenceTemplateMessage } from '../i18n/cycleDefenceTemplate.js';

const bundle = await build({
  entryPoints: [fileURLToPath(new URL('./cycleOperationsService.js', import.meta.url))],
  bundle: true, write: false, format: 'esm', platform: 'node', logLevel: 'silent',
  plugins: [{ name: 'isolated-api', setup(builder) {
    builder.onResolve({ filter: /^\.\/api$/ }, () => ({ path: 'api', namespace: 'template-test' }));
    builder.onLoad({ filter: /.*/, namespace: 'template-test' }, () => ({ contents: `export default {
      async get(url) { return { data: { method: 'GET', url } }; },
      async put(url, payload) { return { data: { method: 'PUT', url, payload } }; },
    };` }));
  } }],
});
const { cycleOperationsService } = await import(`data:text/javascript;base64,${Buffer.from(bundle.outputFiles[0].text).toString('base64')}`);

test('template reads and CAS writes use a separate operations endpoint', async () => {
  const payload = { expected_revision: 0, assignments: [{ user_id: 12, territory_id: 45 }] };
  assert.deepEqual(await cycleOperationsService.getDefenceTemplate(3, 7), {
    method: 'GET', url: '/campaign/cycles/3/clans/7/defence-template',
  });
  assert.deepEqual(await cycleOperationsService.saveDefenceTemplate(3, 7, payload), {
    method: 'PUT', url: '/campaign/cycles/3/clans/7/defence-template', payload,
  });
});

test('template service encodes path parameters', async () => {
  const result = await cycleOperationsService.getDefenceTemplate('3/4', '7?clan=8');
  assert.equal(result.url, '/campaign/cycles/3%2F4/clans/7%3Fclan%3D8/defence-template');
});

test('template copy is localized in ru, en and de without changing global messages', () => {
  const keys = ['heading', 'assignment', 'none', 'empty', 'unavailable', 'save', 'saving', 'saved',
    'dirty', 'reload', 'refresh', 'discard', 'cancel', 'conflict', 'failed', 'reloadFailed'];
  for (const key of keys) {
    assert.notEqual(defenceTemplateMessage(key), key);
    for (const language of ['en', 'de']) {
      const value = defenceTemplateMessage(key, language);
      assert.notEqual(value, key);
      assert.doesNotMatch(value, /[А-Яа-яЁё]/u);
    }
  }
});
