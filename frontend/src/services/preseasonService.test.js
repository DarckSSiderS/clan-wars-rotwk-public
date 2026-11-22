import test from 'node:test';
import assert from 'node:assert/strict';
import { createRequire, Module } from 'node:module';
import { fileURLToPath } from 'node:url';
import { build } from 'esbuild';

const filename = fileURLToPath(new URL('./preseasonService.js', import.meta.url));
const bundle = await build({ entryPoints: [filename], bundle: true, write: false, format: 'cjs', platform: 'node', logLevel: 'silent' });
const compiled = new Module(filename, createRequire(import.meta.url));
compiled.filename = filename;
compiled.paths = Module._nodeModulePaths(fileURLToPath(new URL('../../', import.meta.url)));
compiled._compile(bundle.outputFiles[0].text, filename);
const { preseasonService: service } = compiled.exports;

test('preseason reads and claims use cookie session, correct endpoints and revision without bearer tokens', async t => {
  const requests = [];
  const context = { open: true, clan_id: 7, revision: 5, selected_lands: [1, 2, 3] };
  t.mock.method(globalThis, 'fetch', async (url, init) => { requests.push({ url, init }); return Response.json(context); });
  const controller = new AbortController();
  await service.getStatus(controller.signal);
  await service.getContext(7, controller.signal);
  await service.previewLands(7, [1, 2, 3]);
  assert.deepEqual(await service.chooseLands(7, [1, 2, 3], 4), context);
  await service.chooseRelics(7, ['royal_charter', 'white_tree'], 5);
  assert.deepEqual(requests.map(r => r.url), ['/api/v1/campaign/preseason/status', '/api/v1/campaign/preseason/clans/7', '/api/v1/campaign/preseason/clans/7/lands/preview', '/api/v1/campaign/preseason/clans/7/lands', '/api/v1/campaign/preseason/clans/7/relics']);
  assert.deepEqual(requests.map(r => r.init.method), ['GET', 'GET', 'POST', 'POST', 'POST']);
  assert.deepEqual(requests.slice(2).map(r => JSON.parse(r.init.body)), [{ selected: [1, 2, 3] }, { selected: [1, 2, 3], expected_revision: 4 }, { selected: ['royal_charter', 'white_tree'], expected_revision: 5 }]);
  for (const { init } of requests) { assert.equal(init.credentials, 'include'); assert.equal(init.headers.has('authorization'), false); }
  assert.equal(requests[1].init.signal, controller.signal);
});
test('preseason transport rejects a conflict instead of treating it as an updated context', async t => {
  t.mock.method(globalThis, 'fetch', async () => Response.json({ detail: 'Revision conflict' }, { status: 409 }));
  await assert.rejects(service.chooseLands(7, [1, 2, 3], 4), { status: 409 });
});

test('preseason rejection preserves server string detail for an escaped UI alert', async t => {
  const detail = 'Сохраните прежние земли. <img src=x onerror=alert(1)>';
  t.mock.method(globalThis, 'fetch', async () => Response.json({ detail }, { status: 409 }));
  await assert.rejects(service.previewLands(7, [1, 2, 3]), { status: 409, detail });
});

test('nonstring, empty and non-JSON rejections retain status without exposing an unsafe detail', async t => {
  let response;
  t.mock.method(globalThis, 'fetch', async () => response);
  for (const detail of [{ error: 'internal' }, ['validation'], 5, null, '', '  ']) {
    response = Response.json({ detail }, { status: 422 });
    await assert.rejects(service.previewLands(7, [1, 2, 3]), error => error.status === 422 && !error.detail);
  }
  response = new Response('<html>Bad gateway</html>', { status: 502 });
  await assert.rejects(service.previewLands(7, [1, 2, 3]), error => error.status === 502 && !error.detail);
});
