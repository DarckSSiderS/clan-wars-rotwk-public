import test from 'node:test';
import assert from 'node:assert/strict';
import { dispatchState, reinforcementCommand, dispatchTargetKey, reinforcementMessage } from './cycleReinforcementView.js';
import * as view from './cycleReinforcementView.js';

test('command ids survive retries and revisions but not changed payloads', () => {
  const target = { recipient_clan_id: 7, territory_id: 10, request_id: 'ally-request' };
  const first = reinforcementCommand(null, 'dispatch', target, [3, 2], () => 'first');
  const retry = reinforcementCommand(first, 'dispatch', target, [2, 3], () => 'second');
  assert.equal(retry.id, 'first');
  assert.equal(reinforcementCommand(retry, 'dispatch', target, [2], () => 'third').id, 'third');
  assert.notEqual(dispatchTargetKey(target), dispatchTargetKey({ ...target, request_id: 'new-request' }));
});
test('arrival does not override blocked or pending interception', () => {
  const dispatch = { sent_at: '2026-10-17T00:00:00Z', arrives_at: '2026-10-18T00:00:00Z', outcome: 'clear' };
  const after = Date.parse('2026-10-18T01:00:00Z');
  assert.equal(dispatchState(dispatch, after), 'arrived');
  assert.equal(dispatchState({ ...dispatch, outcome: 'blocked' }, after), 'blocked');
  assert.equal(dispatchState({ ...dispatch, outcome: 'pending' }, after), 'pending');
  assert.equal(dispatchState({ ...dispatch, outcome: 'exhausted' }, after), 'arrivedExhausted');
  assert.equal(dispatchState(dispatch, Date.parse('2026-10-17T01:00:00Z')), 'travelling');
});
test('dispatch retry key includes the selected origin independently of destination', () => {
  const target = { recipient_clan_id: 7, territory_id: 10, request_id: 'q', origin_territory_id: 1 };
  const first = reinforcementCommand(null, 'dispatch', target, [2], () => 'first');
  assert.equal(reinforcementCommand(first, 'dispatch', { ...target }, [2], () => 'retry').id, 'first');
  assert.equal(reinforcementCommand(first, 'dispatch', { ...target, origin_territory_id: 3 }, [2], () => 'changed').id, 'changed');
  assert.equal(reinforcementCommand(first, 'dispatch', { ...target, origin_territory_id: null }, [2], () => 'landless').id, 'landless');
});
test('player-facing statuses never expose raw outcome codes', () => {
  for (const key of ['blocked', 'pending', 'arrived', 'arrivedExhausted', 'travelling']) {
    assert.notEqual(reinforcementMessage(key, 'ru'), key);
    assert.notEqual(reinforcementMessage(key, 'en'), key);
  }
});
test('geographic line uses every graph node in order, never a direct fabricated shortcut', () => {
  assert.equal(typeof view.dispatchRouteDrawing, 'function');
  const route = { status: 'mapped', origin_territory_id: 1, target_territory_id: 3,
    territory_ids: [1, 2, 3], nodes: [{ territory_id: 1 }, { territory_id: 2 }, { territory_id: 3 }] };
  const boxes = new Map([[1, { x: 0, y: 0, width: 10, height: 10 }],
    [2, { x: 10, y: 20, width: 10, height: 10 }], [3, { x: 20, y: 0, width: 10, height: 10 }]]);
  assert.deepEqual(view.dispatchRouteDrawing(route, boxes).points, [[5, 5], [15, 25], [25, 5]]);
  assert.equal(view.dispatchRouteDrawing(route, new Map([...boxes].filter(([id]) => id !== 2))), null);
  assert.equal(view.dispatchRouteDrawing(null, boxes), null);
  for (const status of ['unreachable', 'no_origin']) {
    const targetOnly = view.dispatchRouteDrawing({ ...route, status, territory_ids: [], nodes: [{ territory_id: 3 }] }, boxes);
    assert.deepEqual(targetOnly.points, []);
    assert.deepEqual(targetOnly.target, [25, 5]);
  }
});
test('movement timer counts down to the fixed arrival time', () => {
  assert.equal(typeof view.dispatchCountdown, 'function');
  const dispatch = { arrives_at: '2026-10-18T12:00:00Z' };
  assert.equal(view.dispatchCountdown(dispatch, Date.parse('2026-10-17T12:00:00Z')), '24:00:00');
  assert.equal(view.dispatchCountdown(dispatch, Date.parse('2026-10-18T11:59:59Z')), '00:00:01');
  assert.equal(view.dispatchCountdown(dispatch, Date.parse(dispatch.arrives_at)), '00:00:00');
});
