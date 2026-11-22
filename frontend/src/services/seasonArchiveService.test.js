import test from 'node:test';
import assert from 'node:assert/strict';
import { createRequire, Module } from 'node:module';
import { fileURLToPath } from 'node:url';
import { build } from 'esbuild';

const filename = fileURLToPath(new URL('./seasonArchiveService.js', import.meta.url));
const bundle = await build({ entryPoints: [filename], bundle: true, write: false, format: 'cjs', platform: 'node', logLevel: 'silent' });
const compiled = new Module(filename, createRequire(import.meta.url));
compiled.filename = filename;
compiled.paths = Module._nodeModulePaths(fileURLToPath(new URL('../../', import.meta.url)));
compiled._compile(bundle.outputFiles[0].text, filename);
const { listSeasonArchives, getSeasonArchive } = compiled.exports;
const payload = { season: { id: 1 }, schema_version: 1, view_box: '0 0 3570.6 2339.7', territories: [], clans: [], map_image_url: '/api/v1/campaign/archives/1/map.svg' };

test('public archive service performs GET without credentials and forwards cancellation', async t => {
  const controller = new AbortController();
  const requests = [];
  t.mock.method(globalThis, 'fetch', async (url, init) => {
    requests.push({ url, init });
    return Response.json(url.endsWith('/1') ? payload : { seasons: [{ id: 1 }] });
  });
  assert.deepEqual(await listSeasonArchives(controller.signal), [{ id: 1 }]);
  assert.deepEqual(await getSeasonArchive('1', controller.signal), payload);
  assert.deepEqual(requests.map(row => row.url), ['/api/v1/campaign/archives', '/api/v1/campaign/archives/1']);
  for (const { init } of requests) {
    assert.equal(init.method, 'GET');
    assert.equal(init.credentials, 'omit');
    assert.equal(init.signal, controller.signal);
    assert.equal(init.headers, undefined);
    assert.equal(init.body, undefined);
  }
});

test('invalid archive ID never reaches transport', async t => {
  const transport = t.mock.method(globalThis, 'fetch', () => { throw new Error('Unexpected request'); });
  await assert.rejects(getSeasonArchive('../clans'));
  assert.equal(transport.mock.callCount(), 0);
});

test('HTTP failure preserves not-found status and does not expire an auth session', async t => {
  t.mock.method(globalThis, 'fetch', async () => new Response('{}', { status: 404 }));
  await assert.rejects(getSeasonArchive(1), { status: 404 });
});

test('invalid list, mismatched season, schema and backdrop are rejected instead of loading live data', async t => {
  let response = { seasons: null };
  t.mock.method(globalThis, 'fetch', async () => Response.json(response));
  await assert.rejects(listSeasonArchives());
  for (const change of [{ season: { id: 2 } }, { schema_version: 2 }, { map_image_url: '/map.svg' }, { view_box: '0 0 0 20' }, { clans: null }]) {
    response = { ...payload, ...change };
    await assert.rejects(getSeasonArchive(1));
  }
});
