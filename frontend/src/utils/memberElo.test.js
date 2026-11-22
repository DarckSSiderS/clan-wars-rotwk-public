import test from 'node:test';
import assert from 'node:assert/strict';

import { getMemberEloForPatch, getMemberEloRatings } from './memberElo.js';

test('возвращает Elo обоих модов независимо от предпочтения клана', () => {
  const ratings = getMemberEloRatings({
    elo_patch: 'ennorath',
    elo_ratings: { ennorath: 1210, patch_202: 1375 },
  });

  assert.deepEqual(ratings, {
    ennorath: 1210,
    patch202: 1375,
  });
});

test('подставляет тире для отсутствующего рейтинга', () => {
  assert.deepEqual(getMemberEloRatings({ elo_ratings: {} }), {
    ennorath: '—',
    patch202: '—',
  });
});

test('не смешивает рейтинг выбранного патча с другим', () => {
  const stats = { elo_ratings: { ennorath: 1210, patch_202: 1375 } };

  assert.equal(getMemberEloForPatch(stats, 'ennorath'), 1210);
  assert.equal(getMemberEloForPatch(stats, 'patch_202'), 1375);
  assert.equal(getMemberEloForPatch(stats, 'unknown'), '—');
});
