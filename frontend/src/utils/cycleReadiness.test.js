import test from 'node:test';
import assert from 'node:assert/strict';
import { cycleReadiness } from './cycleReadiness.js';

test('readiness counts only eligible unassigned IDs, actual defenders, reserves, scout and selected relics', () => {
  const planning = { snapshot_ready: true, clan_id: 2, members: [
    { user_id: 1, eligible: true }, { user_id: 2, eligible: true },
    { user_id: 3, eligible: false, scouting: true }, { user_id: 4, eligible: false },
    { user_id: 5, eligible: true }, { user_id: 6, eligible: true }],
  plan: { orders: [{ user_id: 1, kind: 'defend', territory_id: 10 },
    { user_id: 2, kind: 'reserve' }, { user_id: 4, kind: 'defend', territory_id: 11 },
    { user_id: 5, kind: 'ambush', territory_id: 11 }] }, defence_targets: [10, 11, 12] };
  assert.deepEqual(cycleReadiness(planning, { scout: { request: { scout_user_id: 3 } } },
    { state: { active_relics: ['tree', 'horn'], relics: { tree: 1, horn: 2, other: 3 } } }),
  { free: 1, uncovered: 2, reserve: 1, scout: 'assigned', relics: 2 });
});

test('missing context is unknown, not zero readiness; a legacy scout without player is explicit', () => {
  assert.equal(cycleReadiness(null, null, null), null);
  assert.equal(cycleReadiness({ snapshot_ready: false }, {}, {}), null);
  assert.deepEqual(cycleReadiness({ snapshot_ready: true, members: [], plan: { orders: [] }, defence_targets: [] },
    { scout: { request: { scout_user_id: null } } }, {}),
  { free: 0, uncovered: 0, reserve: 0, scout: 'unassigned', relics: null });
});

test('readiness includes validated defence fallback without overriding manual assignments', () => {
  const planning = { snapshot_ready: true, members: [1, 2, 3].map(user_id => ({ user_id, eligible: true })),
    plan: { orders: [{ user_id: 1, kind: 'reserve' }] }, defence_targets: [10, 11],
    defence_template: { fallback_orders: [
      { user_id: 2, kind: 'defend', territory_id: 10 },
      { user_id: 1, kind: 'defend', territory_id: 11 },
      { user_id: 999, kind: 'defend', territory_id: 11 },
    ] } };
  assert.deepEqual(cycleReadiness(planning, {}, {}),
    { free: 1, uncovered: 1, reserve: 1, scout: null, relics: null });
});
