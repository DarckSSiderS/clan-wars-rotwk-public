import test from 'node:test';
import assert from 'node:assert/strict';
import { squadGroups, assignSquad, attackDrawing, battleStatus, visibleHelpRequests, placeMapLabel } from './cycleTacticalView.js';

test('squads group by mission, target, origin and transport, never by nickname', () => {
  const order = { kind: 'attack', territory_id: 20, source_id: 10, route: 'land' };
  const groups = squadGroups([{ user_id: 1, ...order }, { user_id: 2, ...order },
    { user_id: 3, ...order, route: 'sea' }]);
  assert.equal(groups.length, 2);
  assert.deepEqual(groups[0].user_ids, [1, 2]);
});

test('bulk assignment replaces selected ids atomically and leaves other orders alone', () => {
  const rows = [{ user_id: 1, kind: 'reserve' }, { user_id: 9, kind: 'reserve' }];
  const next = assignSquad(rows, [1, 2], { kind: 'defend', territory_id: 10 });
  assert.equal(next.length, 3);
  assert.equal(next.find(row => row.user_id === 1).kind, 'defend');
  assert.deepEqual(next.find(row => row.user_id === 9), rows[1]);
  assert.deepEqual(assignSquad(next, [1, 2], null), [rows[1]]);
});

test('attack arrow ends before territory center; no invented landless origin', () => {
  const boxes = new Map([[10, { x: 0, y: 0, width: 100, height: 100 }],
    [20, { x: 500, y: 0, width: 100, height: 100 }]]);
  assert.equal(attackDrawing({ source_territory_id: null, target_territory_id: 20 }, boxes), null);
  assert.equal(attackDrawing({ source_territory_id: 999, target_territory_id: 20 }, boxes), null);
  const result = attackDrawing({ source_territory_id: 10, target_territory_id: 20 }, boxes);
  assert.ok(result.end[0] < 550 && result.end[0] > result.start[0]);
  assert.equal(result.angle, 0);
});

test('defence alone is not presented as fighting; neutral claims are distinct', () => {
  assert.equal(battleStatus({ owner_clan_id: 1, sides: [{ clan_id: 1 }] }), 'defense');
  assert.equal(battleStatus({ owner_clan_id: null, sides: [{ clan_id: 1 }] }), 'neutral_claim');
  assert.equal(battleStatus({ owner_clan_id: null, sides: [{ clan_id: 1 }, { clan_id: 2 }] }), 'contested');
  assert.equal(battleStatus({ completed: true }), 'completed');
});

test('expired help requests are not presented as live map beacons', () => {
  const data = { phase: 'battle', server_time: '2026-10-29T10:00:00Z', command_deadline: '2026-10-29T11:00:00Z', requests: [{ id: 1 }] };
  assert.equal(visibleHelpRequests(data).length, 1);
  assert.deepEqual(visibleHelpRequests({ ...data, phase: 'settlement' }), []);
  assert.deepEqual(visibleHelpRequests({ ...data, command_deadline: data.server_time }), []);
});

test('route labels avoid already occupied battle and label bounds', () => {
  const occupied = [{ x: 0, y: 0, width: 300, height: 200 }];
  const a = placeMapLabel([150, 80], 'Clan alpha', occupied);
  const b = placeMapLabel([150, 80], 'Clan bravo', occupied);
  assert.notDeepEqual(a, b);
  assert.ok(a.y < 0 || a.y > 200 || a.x < 0 || a.x > 300);
});
