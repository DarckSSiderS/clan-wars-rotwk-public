import test from 'node:test';
import assert from 'node:assert/strict';
import { assignPlayer, planProblem, planCounts, routeKey } from './cyclePlanningView.js';

const data = { members: [{ user_id: 1, eligible: true }, { user_id: 2, eligible: true, reserve_blocked: true },
  { user_id: 3, eligible: true }], limits: { attacks: 1, reserves: 1, ambush_players: 2 },
  defence_targets: [10], attack_routes: [{ territory_id: 20, source_id: 10, route: 'land' }] };

test('assignments use stable player ids and replace rather than duplicate', () => {
  const result = assignPlayer([{ user_id: 1, kind: 'reserve' }], 1, { kind: 'defend', territory_id: 10 });
  assert.equal(result.length, 1);
  assert.equal(result[0].user_id, 1);
  assert.equal(result[0].kind, 'defend');
  assert.deepEqual(assignPlayer(result, 1, null), []);
});
test('reserves obey cooldown and capacity', () => {
  assert.equal(planProblem([{ user_id: 2, kind: 'reserve' }], data), 'reserveBlocked');
  assert.equal(planProblem([{ user_id: 1, kind: 'reserve' }, { user_id: 3, kind: 'reserve' }], data), 'reserveLimit');
});

test('scouting members cannot receive any combat or reserve assignment', () => {
  const scouting = { ...data, members: [{ user_id: 1, eligible: true, scouting: true }] };
  for (const kind of ['attack', 'defend', 'reserve', 'ambush']) {
    assert.equal(planProblem([{ user_id: 1, kind, territory_id: 10 }], scouting), 'scouting');
  }
  assert.equal(planProblem([], scouting), null);
});
test('ambush requires ordinary squad on same land and only one destination', () => {
  assert.equal(planProblem([{ user_id: 1, kind: 'ambush', territory_id: 10 }], data), 'ambushSquad');
  assert.equal(planProblem([{ user_id: 1, kind: 'defend', territory_id: 10 }, { user_id: 3, kind: 'ambush', territory_id: 10 }], data), null);
});
test('legal routes include source and transport; counters count destinations not players', () => {
  const attack = { kind: 'attack', territory_id: 20, source_id: 10, route: 'land' };
  assert.notEqual(routeKey(attack), routeKey({ ...attack, route: 'sea' }));
  assert.equal(planProblem([{ user_id: 1, ...attack, source_id: 999 }], data), 'routeInvalid');
  assert.equal(planCounts([{ user_id: 1, ...attack }, { user_id: 3, ...attack }]).attacks, 1);
});
