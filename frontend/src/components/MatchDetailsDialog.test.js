import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';

test('match images and replay download remain inside the private preview namespace', () => {
  const source = readFileSync(new URL('./MatchDetailsDialog.jsx', import.meta.url), 'utf8');
  assert.equal((source.match(/src=\{withAppBase\(match\.map_preview_url\)\}/g) || []).length, 2);
  assert.ok(source.includes('href={withAppBase(match.replay_download_url)}'));
});
