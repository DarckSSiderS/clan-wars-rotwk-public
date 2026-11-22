import assert from 'node:assert/strict';
import test from 'node:test';

import {
  getAchievementPresentation,
  normalizeAchievementTier,
} from '../src/utils/achievementPresentation.js';

test('обычная редкость завершенного достижения отображается бронзовой ступенью', () => {
  assert.equal(normalizeAchievementTier('common'), 'bronze');
  assert.equal(normalizeAchievementTier('rare'), 'silver');
  assert.equal(normalizeAchievementTier('epic'), 'gold');
  assert.equal(normalizeAchievementTier('legendary'), 'crystal');
});

test('карты получают стабильное и отличимое оформление', () => {
  const first = getAchievementPresentation('map_games_fords_of_isen', 'Битвы на Бродах Изена');
  const repeat = getAchievementPresentation('map_games_fords_of_isen', 'Битвы на Бродах Изена');
  const other = getAchievementPresentation('map_games_buckland', 'Битвы в Бакленде');

  assert.deepEqual(first, repeat);
  assert.notEqual(first.accent, other.accent);
  assert.equal(first.kind, 'map');
});
