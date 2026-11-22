import test from 'node:test';
import assert from 'node:assert/strict';
import * as view from './cycleInterceptionView.js';
const {
  interceptionMessage, interceptionPath, interceptionReviewMessage, canRestoreInterceptionContribution,
  canChangeInterceptionOutcome, canConfirmInterceptionOutcome, createInterceptionCommandStore,
} = view;

test('interception links preserve a dispatch command as one encoded query value', () => {
  const path = interceptionPath(1, 'route / 1?x#fragment');
  assert.equal(new URL(path, 'https://local.test').searchParams.get('dispatch'), 'route / 1?x#fragment');
  assert.equal(new URL(path, 'https://local.test').hash, '');
});

test('interception outcomes and roles have player-facing bilingual labels', () => {
  for (const key of ['screen', 'pending', 'blocked', 'exhausted', 'battle', 'completed', 'help', 'ambush']) {
    assert.notEqual(interceptionMessage(key, 'ru'), '-');
    assert.notEqual(interceptionMessage(key, 'en'), '-');
    assert.notEqual(interceptionMessage(key, 'ru'), key);
  }
});

test('исход можно подтвердить только с актуальной версией и строго до прибытия', () => {
  const data = { revision: 3, server_time: '2026-10-20T23:59:59Z',
    arrives_at: '2026-10-21T00:00:00Z', replay_deadline: '2026-10-20T14:05:00Z' };
  assert.equal(canChangeInterceptionOutcome(data, 999), true);
  assert.equal(canChangeInterceptionOutcome(data, 1000), false);
  assert.equal(canConfirmInterceptionOutcome(data, { revision: 3 }, 999), true);
  assert.equal(canConfirmInterceptionOutcome(data, { revision: 2 }), false);
  assert.equal(canChangeInterceptionOutcome({ ...data, arrives_at: 'invalid' }), false);
});

test('неточное Elo не позволяет вернуть матч в зачёт по текущему rating', () => {
  const row = { reason: 'missing_historical_elo', calculation: { historical_elo: null, rating: 951, oldRank: 665 } };
  assert.equal(canRestoreInterceptionContribution(row), false);
  assert.equal(canRestoreInterceptionContribution({ ...row, reason: 'counted' }), false);
  assert.equal(canRestoreInterceptionContribution({ reason: 'counted', calculation: { historical_elo: '951' } }), true);
  assert.notEqual(interceptionReviewMessage('missing_elo'), '-');
});

test('команда сохраняется при сетевом повторе и перезагрузке без подмены revision', () => {
  const cache = new Map();
  const storage = { getItem: key => cache.get(key), setItem: (key, value) => cache.set(key, value) };
  let ids = 0;
  const make = () => `cmd-${++ids}`;
  const payload = { expected_revision: 2, reason: 'Пересмотр', counted: false };
  const commands = createInterceptionCommandStore(storage, 'actor:cycle:dispatch', make);
  const first = commands.get('review', payload);
  assert.equal(commands.get('review', { counted: false, reason: 'Пересмотр', expected_revision: 2 }), first);
  const restored = createInterceptionCommandStore(storage, 'actor:cycle:dispatch', make);
  assert.equal(restored.get('review', payload), first);
  assert.notEqual(restored.get('confirm', payload), first);
  assert.notEqual(restored.get('review', { ...payload, expected_revision: 3 }), first);
  assert.notEqual(createInterceptionCommandStore(storage, 'other', make).get('review', payload), first);
});

test('неопределённый сетевой ответ сохраняет исходное тело команды при обновлении данных', () => {
  const cache = new Map();
  const storage = { getItem: key => cache.get(key), setItem: (key, value) => cache.set(key, value) };
  const payload = { expected_revision: 2, amount: '100', reason: 'Поправка', side_clan_id: 5 };
  const commands = createInterceptionCommandStore(storage, 'actor:cycle:dispatch', () => 'stable');
  const submitted = commands.prepare('adjust', payload);
  const restored = createInterceptionCommandStore(storage, 'actor:cycle:dispatch', () => 'new');
  assert.deepEqual(restored.prepare('adjust', { ...payload, expected_revision: 3 }), submitted);
  assert.equal(submitted.expected_revision, 2);
  restored.settle('adjust', payload);
  assert.equal(restored.prepare('adjust', { ...payload, expected_revision: 3 }).expected_revision, 3);
});

test('подтверждённый предпросмотр можно выполнить заново с той же revision', () => {
  const cache = new Map();
  const storage = { getItem: key => cache.get(key), setItem: (key, value) => cache.set(key, value) };
  let id = 0;
  const commands = createInterceptionCommandStore(storage, 'scope', () => String(++id));
  const payload = { expected_revision: 2, reason: 'Проверка' };
  const first = commands.prepare('preview', payload);
  commands.settle('preview', payload);
  assert.notEqual(commands.prepare('preview', payload).command_id, first.command_id);
});
