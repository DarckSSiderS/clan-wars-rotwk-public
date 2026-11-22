import test from 'node:test';
import assert from 'node:assert/strict';
import { clanCycleBattle, currentClanBattles } from './clanCycleHistory.js';

test('cycle rows preserve all opponents, decimal scores and actual cycle/territory links', () => {
  const row = clanCycleBattle({ id: 8, cycle_id: 17, territory_id: 4, season_id: 2,
    completed_at: null, sides: [{ clan_id: 2, score: '1.25' },
      { clan_id: 3, clan_name: 'Other', score: '-3.5' }, { clan_id: 4, clan_name: 'Third', score: '9' }] }, 2);
  assert.equal(row.href, '/campaign/cycles/17?territory=4');
  assert.equal(row.ownScore, '1.25');
  assert.deepEqual(row.opponents.map(side => side.clan_name), ['Other', 'Third']);
  assert.equal(row.result, 'active');
});

test('unfinished, neutral and won outcomes are not conflated; latest season overview excludes archives', () => {
  const row = { id: 1, cycle_id: 9, territory_id: 4, season_id: 2, completed_at: '2026-10-31', sides: [] };
  assert.equal(clanCycleBattle(row, 2).result, 'draw');
  assert.equal(clanCycleBattle({ ...row, winner_clan_id: 2 }, '2').result, 'win');
  assert.equal(clanCycleBattle({ ...row, winner_clan_id: 3 }, 2).result, 'loss');
  assert.deepEqual(currentClanBattles({ season_id: 2, battles: [row, { ...row, id: 2, season_id: 1 }] }), [row]);
});

test('database Decimal scores are readable without losing exact fractional points', () => {
  const row = clanCycleBattle({ cycle_id: 1, territory_id: 2,
    sides: [{ clan_id: 2, score: '0E-12' }, { clan_id: 3, score: '300.000000000000' },
      { clan_id: 4, score: '0.000000000001' }] }, 2);
  assert.equal(row.ownScore, '0');
  assert.deepEqual(row.opponents.map(side => side.score), ['300', '0.000000000001']);
});
