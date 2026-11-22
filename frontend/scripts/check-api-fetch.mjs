import { readFile, readdir } from 'node:fs/promises';
import path from 'node:path';
import process from 'node:process';
import { publicAssetCredentials } from '../src/utils/appBasePath.js';

const sourceRoot = path.resolve('src');
const transportPath = path.join('services', 'apiFetch.js');
const sourceExtensions = new Set(['.js', '.jsx']);

const listSourceFiles = async (directory) => {
  const entries = await readdir(directory, { withFileTypes: true });
  const files = await Promise.all(entries.map(async (entry) => {
    const entryPath = path.join(directory, entry.name);
    if (entry.isDirectory()) return listSourceFiles(entryPath);
    return sourceExtensions.has(path.extname(entry.name)) ? [entryPath] : [];
  }));
  return files.flat();
};

const failures = [];
for (const filePath of await listSourceFiles(sourceRoot)) {
  const relativePath = path.relative(sourceRoot, filePath);
  if (relativePath === transportPath) continue;
  const source = await readFile(filePath, 'utf8');
  if (/\bfetch\s*\(/u.test(source)) {
    failures.push(`${relativePath}: прямой fetch запрещен`);
  }
  if (/Authorization/u.test(source)) {
    failures.push(`${relativePath}: Authorization header запрещен`);
  }
  let nonAssetPublicFetch = source.replaceAll(
    "publicFetch('/map-interactive.svg')",
    '',
  );
  if (relativePath === path.join('services', 'seasonArchiveService.js')) {
    nonAssetPublicFetch = nonAssetPublicFetch.replace(
      "publicFetch(archiveEndpoint(seasonId), { method: 'GET', signal })", '',
    );
  }
  if (/publicFetch\s*\(/u.test(nonAssetPublicFetch)) {
    failures.push(`${relativePath}: publicFetch разрешен только для публичного SVG`);
  }
}

let transportSource = '';
try {
  transportSource = await readFile(path.join(sourceRoot, transportPath), 'utf8');
} catch {
  failures.push(`${transportPath}: единый transport отсутствует`);
}

for (const [pattern, message] of [
  [/credentials:\s*['"]include['"]/u, 'credentials include не закреплен'],
  [/response\.status\s*===\s*401/u, 'обработка 401 отсутствует'],
  [/announceSessionExpired\(\)/u, 'событие истечения сессии не отправляется'],
  [/credentials:\s*publicAssetCredentials\(input\)/u, 'publicFetch должен использовать проверяемую политику cookies ресурсов'],
]) {
  if (!pattern.test(transportSource)) failures.push(`${transportPath}: ${message}`);
}

for (const [url, base, expected] of [
  ['/map-interactive.svg', '/', 'omit'],
  ['/encyclopedia/ennorath/catalog.json', '/', 'omit'],
  ['/map-interactive.svg', '/admin/preview/', 'same-origin'],
  ['/encyclopedia/ennorath/models/test.glb', '/admin/preview/', 'same-origin'],
  ['https://example.com/model.glb', '/admin/preview/', 'omit'],
  ['//example.com/model.glb', '/admin/preview/', 'omit'],
]) {
  if (publicAssetCredentials(url, base) !== expected) {
    failures.push(`${transportPath}: нарушена изоляция cookies публичных ресурсов`);
  }
}

if (failures.length > 0) {
  console.error(failures.join('\n'));
  process.exitCode = 1;
} else {
  console.log('Frontend fetch contract проверен.');
}
