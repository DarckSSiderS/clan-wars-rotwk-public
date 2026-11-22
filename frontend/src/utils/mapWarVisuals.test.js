import assert from 'node:assert/strict';
import test from 'node:test';

import { getWarScoreSplit } from './mapWarVisuals.js';

test('splits a contested territory by each clan war points', () => {
  assert.deepEqual(getWarScoreSplit({
    attacking_clan_id: 10,
    defending_clan_id: 20,
    clan_scores: [
      { clan_id: 10, points: 64 },
      { clan_id: 20, points: 36 },
    ],
  }), {
    attackerPoints: 64,
    defenderPoints: 36,
    attackerShare: 64,
    defenderShare: 36,
  });
});

test('uses an even split before either clan earns points', () => {
  assert.deepEqual(getWarScoreSplit({
    attacking_clan_id: 10,
    defending_clan_id: 20,
    clan_scores: [],
  }), {
    attackerPoints: 0,
    defenderPoints: 0,
    attackerShare: 50,
    defenderShare: 50,
  });
});

test('ignores invalid and negative war points', () => {
  assert.deepEqual(getWarScoreSplit({
    attacking_clan_id: 10,
    defending_clan_id: 20,
    clan_scores: [
      { clan_id: 10, points: -5 },
      { clan_id: 20, points: 'not-a-number' },
    ],
  }), {
    attackerPoints: 0,
    defenderPoints: 0,
    attackerShare: 50,
    defenderShare: 50,
  });
});
