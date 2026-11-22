import test from 'node:test';
import assert from 'node:assert/strict';
import { territoryMatchFeed, battleKind, matchFeedCounts } from './cycleMatchPresentation.js';

test('one replay is one match with separate clan effects and only counted points', () => {
  const battle = { sides: [{ clan_id: 1, clan_name: 'A' }, { clan_id: 2, clan_name: 'B' }],
    contributions: [{ replay_id: 'r', user_id: 1, clan_id: 1, points: '100.125', counted: true },
      { replay_id: 'r', user_id: 2, clan_id: 1, points: '0.125', counted: true },
      { replay_id: 'r', user_id: 3, clan_id: 2, points: '-50.25', counted: true },
      { replay_id: 'r', user_id: 4, clan_id: 2, points: '999', counted: false }] };
  const rows = territoryMatchFeed(battle);
  assert.equal(rows.length, 1);
  assert.equal(rows[0].status, 'mixed');
  assert.deepEqual(rows[0].effects.map(e => e.points), ['100.25', '-50.25']);
  assert.deepEqual(rows[0].teams, []);
  assert.deepEqual(matchFeedCounts(rows), { all: 1, counted: 1, rejected: 0 });
});

test('match teams and winners come from replay, never from score sign or clan membership', () => {
  const battle = { sides: [], contributions: [{ replay_id: 'r', user_id: 1, clan_id: 1, points: '-100', counted: false }],
    matches: [{ replay_id: 'r', played_at: '2026-10-29T12:00:00Z', participants: [
      { user_id: 1, name: 'Winner', team: 1, is_winner: true }, { user_id: 2, name: 'Outside player', team: 2, is_winner: false }] }] };
  const row = territoryMatchFeed(battle)[0];
  assert.equal(row.teams[0].is_winner, true);
  assert.equal(row.teams[1].players[0].name, 'Outside player');
  assert.equal(row.effects[0].points, '0');
  assert.equal(row.status, 'rejected');
});

test('neutral land, defence and contested battles are not all labelled as active fighting', () => {
  assert.equal(battleKind({ sides: [{ role: 'defense' }] }), 'defenseOnly');
  assert.equal(battleKind({ owner_clan_id: null, sides: [{ role: 'attack' }] }), 'neutralClaim');
  assert.equal(battleKind({ sides: [{ role: 'attack' }, { role: 'attack' }] }), 'contested');
});

test('database exponent decimals never crash and retain the smallest stored point', () => {
  const battle = { sides: [{ clan_id: 1, score: '0E-12' }], contributions: [
    { replay_id: 'zero', user_id: 1, clan_id: 1, points: '0E-12', counted: true },
    { replay_id: 'tiny', user_id: 1, clan_id: 1, points: '1E-12', counted: true }] };
  assert.equal(territoryMatchFeed(battle)[0].effects[0].points, '0');
  assert.equal(territoryMatchFeed(battle)[1].effects[0].points, '0.000000000001');
});

test('confirmed calculation start wins over legacy timezone-less match date', () => {
  const battle = { contributions: [{ replay_id: 'r', clan_id: 1, points: '0', counted: false,
    calculation: { started_at: '2026-10-29T12:00:00+00:00' } }],
    matches: [{ replay_id: 'r', played_at: '2026-10-29T12:00:00' }] };
  assert.equal(territoryMatchFeed(battle)[0].played_at, '2026-10-29T12:00:00+00:00');
});
