import { existsSync, readdirSync, readFileSync, statSync } from 'node:fs';
import { join, relative } from 'node:path';

const root = new URL('../src/', import.meta.url);
const sourceRoot = decodeURIComponent(root.pathname).replace(/^\/([A-Za-z]:)/, '$1');
const forbiddenStorageCall = /(?:localStorage|sessionStorage)\.(?:getItem|setItem)\(\s*['"](?:token|user|admin_token|original_admin|admin_impersonation_[^'"]*)['"]/g;
const failures = [];

const visit = (directory) => {
  for (const name of readdirSync(directory)) {
    const path = join(directory, name);
    if (statSync(path).isDirectory()) {
      visit(path);
      continue;
    }
    if (!/\.[jt]sx?$/.test(name)) continue;
    const source = readFileSync(path, 'utf8');
    if (forbiddenStorageCall.test(source)) {
      failures.push(relative(sourceRoot, path));
    }
    forbiddenStorageCall.lastIndex = 0;
  }
};

visit(sourceRoot);
const retiredModule = join(sourceRoot, 'utils', 'impersonationSession.js');
if (existsSync(retiredModule)) failures.push('utils/impersonationSession.js');

if (failures.length) {
  console.error(`Запрещённое клиентское хранение auth-состояния: ${[...new Set(failures)].join(', ')}`);
  process.exit(1);
}

console.log('Auth storage check passed.');
