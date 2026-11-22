import test from 'node:test';
import assert from 'node:assert/strict';
import { treasuryDraft, treasuryCommand, readAdminCommand, rememberAdminCommand, forgetAdminCommand, recoveryCommand, canRecoverPreparation } from './adminCycleCommands.js';

const context = { mechanics_version: 'cycle_v1', season_id: 8, state: {
  season_id: 8, revision: 4, wallet: { gold: '1234.123456789012345678', iron: '42', wood: '30', food: '20', mithril: '5' },
} };
const storage = () => {
  const rows = new Map();
  return { getItem: key => rows.get(key) ?? null, setItem: (key, value) => rows.set(key, value), removeItem: key => rows.delete(key) };
};

test('seasonal form loads exact wallet strings, not Clan legacy balances or influence', () => {
  const draft = treasuryDraft(context, { gold: 777, influence: 900 });
  assert.equal(draft.gold, '1234.123456789012345678');
  assert.equal(draft.influence, undefined);
  const payload = treasuryCommand(context, { ...draft, reason: '  Correct balance  ' });
  assert.deepEqual(payload, { season_id: 8, expected_revision: 4, reason: 'Correct balance', wallet: context.state.wallet });
});

test('legacy form is enabled only by explicitly confirmed legacy mode', () => {
  assert.equal(treasuryDraft({ mechanics_version: 'legacy' }, { gold: 777, influence: 900 }).influence, 900);
  for (const value of [null, {}, { mechanics_version: 'future' }, { mechanics_version: 'cycle_v1', state: null }]) {
    assert.throws(() => treasuryDraft(value, { gold: 777 }));
  }
});

test('invalid or missing amount never becomes zero or a rounded number', () => {
  for (const gold of ['', '-1', 'NaN', 'Infinity', '1e309', 1.25]) {
    assert.throws(() => treasuryCommand(context, { ...context.state.wallet, gold, reason: 'Correct balance' }));
  }
  assert.throws(() => treasuryCommand(context, { ...context.state.wallet, reason: '  ' }));
});

test('uncertain command survives reload and cannot be overwritten with edited terms', () => {
  const cache = storage();
  const payload = treasuryCommand(context, { ...context.state.wallet, reason: 'Correct balance' });
  const first = rememberAdminCommand(cache, 'treasury:actor:1:season:8:clan:2', payload, () => 'first');
  assert.equal(first.command_id, 'first');
  assert.deepEqual(readAdminCommand(cache, 'treasury:actor:1:season:8:clan:2'), first);
  assert.deepEqual(rememberAdminCommand(cache, 'treasury:actor:1:season:8:clan:2', payload, () => 'second'), first);
  assert.throws(() => rememberAdminCommand(cache, 'treasury:actor:1:season:8:clan:2', { ...payload, reason: 'Other reason' }));
  assert.equal(rememberAdminCommand(cache, 'treasury:actor:2:season:8:clan:2', payload, () => 'other').command_id, 'other');
  forgetAdminCommand(cache, 'treasury:actor:1:season:8:clan:2');
  assert.equal(readAdminCommand(cache, 'treasury:actor:1:season:8:clan:2'), null);
});

test('storage failure stops submission before command is sent', () => {
  assert.throws(() => rememberAdminCommand({ getItem: () => null, setItem: () => { throw Error('blocked'); } }, 'test', {}, () => 'id'));
});

test('recovery requires eligibility, explicit confirmation and reason; retry preserves revision', () => {
  const cycle = { id: 3, revision: 9, recovery_available: true };
  assert.throws(() => recoveryCommand({ ...cycle, recovery_available: false }, 'Fix missing snapshot', true));
  assert.throws(() => recoveryCommand(cycle, 'Fix missing snapshot', false));
  assert.throws(() => recoveryCommand(cycle, '  ', true));
  assert.throws(() => recoveryCommand(cycle, 'x'.repeat(501), true));
  const payload = recoveryCommand(cycle, ' Fix missing snapshot ', true);
  assert.deepEqual(payload, { expected_revision: 9, reason: 'Fix missing snapshot' });
  const cache = storage();
  const first = rememberAdminCommand(cache, 'recovery:actor:1:cycle:3', payload, () => 'recover-1');
  assert.equal(readAdminCommand(cache, 'recovery:actor:1:cycle:3').expected_revision, 9);
  assert.equal(rememberAdminCommand(cache, 'recovery:actor:1:cycle:3', payload, () => 'recover-2').command_id, first.command_id);
});

test('a saved recovery remains retryable after the server has already reopened preparation', () => {
  assert.equal(canRecoverPreparation({ id: 7, recovery_available: false }, null), false);
  assert.equal(canRecoverPreparation({ id: 7, recovery_available: true }, null), true);
  assert.equal(canRecoverPreparation({ id: 7, recovery_available: false }, { command_id: 'original' }), true);
  assert.equal(canRecoverPreparation(null, { command_id: 'original' }), false);
});
