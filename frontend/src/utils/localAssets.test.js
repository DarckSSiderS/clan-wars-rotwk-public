import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';

test('страница не зависит от внешней блокирующей таблицы стилей', () => {
  const html = readFileSync(new URL('../../index.html', import.meta.url), 'utf8');
  const styles = html.match(/<link\b[^>]*rel=["']stylesheet["'][^>]*>/gi) || [];
  assert.ok(styles.length > 0);
  assert.ok(styles.every(link => !/href=["'](?:https?:)?\/\//i.test(link)));
});

test('социальные значки используют локальный шрифт с лицензией', () => {
  const css = readFileSync(new URL('../vendor.css', import.meta.url), 'utf8');
  assert.match(css, /fontawesome-brands\.css/);
  const font = readFileSync(new URL('../../public/vendor/fontawesome/fa-brands-400.woff2', import.meta.url));
  assert.equal(font.subarray(0, 4).toString(), 'wOF2');
  const license = readFileSync(new URL('../../public/vendor/fontawesome/LICENSE.txt', import.meta.url), 'utf8');
  assert.match(license, /SIL OFL 1\.1/);
});
