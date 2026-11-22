import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { readFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const root = resolve(dirname(fileURLToPath(import.meta.url)), '../public/encyclopedia/ennorath');
const catalog = JSON.parse(readFileSync(resolve(root, 'catalog.json')));
const manifest = JSON.parse(readFileSync(resolve(root, 'manifest.json')));
assert.equal(catalog.mod, 'ennorath');
assert.equal(catalog.profiles.length, manifest.profiles);
const ids = new Set(catalog.profiles.map((profile) => profile.id));
assert.equal(ids.size, catalog.profiles.length);
catalog.factions.forEach((faction) => faction.entities.forEach((id) => assert.ok(ids.has(id), id)));
for (const [path, hash] of Object.entries(manifest.files)) {
  const bytes = readFileSync(resolve(root, path));
  assert.equal(createHash('sha256').update(bytes).digest('hex'), hash, path);
  if (path.endsWith('.glb')) {
    assert.equal(bytes.toString('utf8', 0, 4), 'glTF', path);
    assert.equal(bytes.readUInt32LE(4), 2, path);
    assert.equal(bytes.readUInt32LE(8), bytes.length, path);
  }
}
function verify(value) {
  if (Array.isArray(value)) return value.forEach(verify);
  if (value && typeof value === 'object') return Object.values(value).forEach(verify);
  if (typeof value !== 'string' || !value.startsWith('/')) return;
  const prefix = '/encyclopedia/ennorath/';
  assert.ok(value.startsWith(prefix), value);
  assert.ok(manifest.files[value.slice(prefix.length)], value);
}
verify(catalog.profiles);
console.log(`Ennorath verified: ${ids.size} profiles, ${Object.keys(manifest.files).length} assets, original SHA-256 hashes match.`);
