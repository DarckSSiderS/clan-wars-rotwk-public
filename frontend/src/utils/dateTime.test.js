import test from 'node:test';
import assert from 'node:assert/strict';
import { asUtcIsoTime, formatMoscowDateTime } from './dateTime.js';

test('legacy match timestamps without a zone retain UTC instead of browser local time', () => {
  assert.equal(asUtcIsoTime('2026-10-29T12:00:00'), '2026-10-29T12:00:00Z');
  assert.equal(asUtcIsoTime('2026-10-29T12:00:00.123'), '2026-10-29T12:00:00.123Z');
  assert.equal(asUtcIsoTime('2026-10-29T12:00:00+03:00'), '2026-10-29T12:00:00+03:00');
  assert.equal(asUtcIsoTime(null), null);
  assert.match(formatMoscowDateTime(asUtcIsoTime('2026-10-29T12:00:00'), '', 'ru'), /15:00/);
});
