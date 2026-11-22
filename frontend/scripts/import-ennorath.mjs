import { createHash } from 'node:crypto';
import { copyFileSync, existsSync, mkdirSync, readFileSync, writeFileSync } from 'node:fs';
import { dirname, relative, resolve } from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';
import { runInNewContext } from 'node:vm';

// Import a trusted local checkout; the standalone application is never modified.
const source = resolve(process.argv[2] || '../website-viewer');
const frontend = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const output = resolve(frontend, 'public/encyclopedia/ennorath');
const main = readFileSync(resolve(source, 'src/main.js'), 'utf8');
const batches = {};
for (const number of ['01', '02', '03', '04']) {
  Object.assign(batches, await import(pathToFileURL(resolve(source, `src/transfer-batch-${number}.js`))));
}
const start = main.indexOf('const animations =');
const end = main.indexOf("document.querySelector('#app').innerHTML");
if (start < 0 || end <= start) throw new Error('Unrecognized archive source structure');
const { heroProfiles, libraries } = runInNewContext(
  `${main.slice(start, end)}; ({ heroProfiles, libraries });`, batches,
);
const factions = libraries.ennorath.factions;
const ids = [...new Set(factions.flatMap((faction) => faction.entities))];
const assets = new Map();
function transfer(value) {
  if (Array.isArray(value)) return value.map(transfer);
  if (value && typeof value === 'object') return Object.fromEntries(Object.entries(value).map(([key, item]) => [key, transfer(item)]));
  if (typeof value !== 'string' || !/^\/(models|assets)\//.test(value)) return value;
  const file = resolve(source, `public${value}`);
  if (!existsSync(file)) throw new Error(`Missing game asset: ${value}`);
  const target = resolve(output, `.${value}`);
  mkdirSync(dirname(target), { recursive: true });
  copyFileSync(file, target);
  assets.set(value.slice(1), createHash('sha256').update(readFileSync(file)).digest('hex'));
  return `/encyclopedia/ennorath${value}`;
}
const profiles = ids.map((id) => {
  if (!heroProfiles[id]) throw new Error(`Missing profile: ${id}`);
  return transfer(heroProfiles[id]);
});
mkdirSync(output, { recursive: true });
writeFileSync(resolve(output, 'catalog.json'), JSON.stringify({
  mod: 'ennorath', sourceLanguage: 'ru', factions, profiles,
}, null, 2) + '\n');
writeFileSync(resolve(output, 'manifest.json'), JSON.stringify({
  sourceProject: 'website-viewer', profiles: profiles.length,
  files: Object.fromEntries([...assets].sort(([a], [b]) => a.localeCompare(b))),
}, null, 2) + '\n');
console.log(`Imported ${profiles.length} Ennorath profiles and ${assets.size} assets into ${relative(frontend, output)}`);
