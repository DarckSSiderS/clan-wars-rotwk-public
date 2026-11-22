import test from 'node:test';
import assert from 'node:assert/strict';
import { startCyclePoll } from './cycleBattlePolling.js';

function setup() {
  let timer, listener;
  const requests = [], values = [], errors = [];
  const visibility = { hidden: false, addEventListener: (_, fn) => { listener = fn; }, removeEventListener: () => { listener = null; } };
  const poll = startCyclePoll({
    load: signal => new Promise((resolve, reject) => requests.push({ resolve, reject, signal })),
    onData: data => values.push(data), onError: error => errors.push(error),
    visibility, schedule: fn => { timer = fn; return 1; }, cancel: () => { timer = null; },
  });
  return { poll, requests, values, errors, tick: () => timer?.(),
    visible(hidden) { visibility.hidden = hidden; listener?.(); } };
}
const flush = async () => { for (let i = 0; i < 6; i++) await Promise.resolve(); };

test('poll is single flight; retries are bounded and refresh errors retain last data', async () => {
  const s = setup();
  s.poll.refresh(); s.poll.refresh();
  assert.equal(s.requests.length, 1);
  s.requests[0].resolve('first'); await flush();
  assert.deepEqual(s.values, ['first']);
  assert.equal(s.requests.length, 2);
  s.requests[1].reject(new Error('offline')); await flush();
  assert.deepEqual(s.values, ['first']);
  assert.equal(s.errors.length, 1);
  s.tick(); assert.equal(s.requests.length, 3);
  s.poll.stop();
});

test('hidden tab does not poll; visible resumes, cleanup aborts and rejects stale results', async () => {
  const s = setup();
  s.requests[0].resolve(1); await flush();
  s.visible(true); s.tick(); s.poll.refresh();
  assert.equal(s.requests.length, 1);
  s.visible(false); assert.equal(s.requests.length, 2);
  s.poll.stop();
  assert.equal(s.requests[1].signal.aborted, true);
  s.requests[1].resolve(2); await flush();
  assert.deepEqual(s.values, [1]);
});

test('a command result invalidates an older GET without starting overlapping GETs', async () => {
  const s = setup();
  s.poll.invalidate();
  s.requests[0].resolve('old'); await flush();
  assert.deepEqual(s.values, []);
  s.tick(); s.requests[1].resolve('new'); await flush();
  assert.deepEqual(s.values, ['new']);
  s.poll.stop();
});
