import test from 'node:test';
import assert from 'node:assert/strict';
import { groupClanBattles, groupContributions, formatScore, createAdjustmentCommand, cycleMessage, cyclePhaseLabel, cycleReasonLabel, reviewCounted, selectTerritoryBattle } from './cycleBattleView.js';

test('territory link selects the matching battle and prefers the current user clan', () => {
  const battles = [{ id: 1, territory_id: 10, sides: [{ clan_id: 1 }] },
    { id: 2, territory_id: 20, sides: [{ clan_id: 2 }, { clan_id: 3 }, { clan_id: 4 }] }];
  for (const user of [{ clan_id: 4 }, { clan: { id: '4' } }, { current_clan_id: 4 }, { current_clan: { id: 4 } }]) {
    assert.deepEqual(selectTerritoryBattle(battles, '20', user), { battle: battles[1], clan_id: 4 });
  }
  assert.equal(selectTerritoryBattle(battles, '20', { clan_id: 99 }).clan_id, 2);
  assert.equal(selectTerritoryBattle(battles, '20').clan_id, 2);
  assert.equal(selectTerritoryBattle(battles, '20', { current_clan_id: 3, clan_id: 4 }).clan_id, 3);
});

test('missing, invalid, or unmatched territory links do not select a battle', () => {
  const battles = [{ id: 1, territory_id: 10, sides: [] }];
  for (const territory of [null, '', 'bad', '-10', '1e1', '99', '10.0']) {
    assert.equal(selectTerritoryBattle(battles, territory), null);
  }
  assert.deepEqual(selectTerritoryBattle(battles, '10'), { battle: battles[0], clan_id: null });
  assert.equal(selectTerritoryBattle([], '10'), null);
});

test('cycle messages default to Russian and switch to English', () => {
  assert.equal(cycleMessage('cycle_battles_title'), 'Битвы цикла');
  assert.equal(cycleMessage('cycle_battles_title', 'en'), 'Cycle battles');
  assert.equal(cycleMessage('common_save', 'ru'), 'Сохранить');
  assert.equal(cycleMessage('common_save', 'en-GB'), 'Save');
});

test('all serialized phases have human labels and unknown phases hide codes', () => {
  for (const phase of ['scheduled', 'registration', 'preparation', 'battle', 'replay_loading', 'settlement', 'rest', 'complete', 'season_ended']) {
    assert.notEqual(cyclePhaseLabel(phase), phase);
    assert.notEqual(cyclePhaseLabel(phase, 'en'), phase);
  }
  assert.equal(cyclePhaseLabel('future_phase'), 'Статус пока недоступен');
  assert.equal(cyclePhaseLabel('battle', 'en'), 'Battles');
});

test('scoring reasons are localized without losing free-form admin reasons', () => {
  assert.equal(cycleReasonLabel('missing_historical_elo'), 'Нет рейтинга Elo на момент матча');
  assert.equal(cycleReasonLabel('missing_historical_elo', 'en'), 'Historical match Elo is unavailable');
  for (const code of ['not_assigned', 'clan_opponent', 'allied_opponent', 'draw', 'unknown_result', 'counted']) {
    assert.notEqual(cycleReasonLabel(code), code);
    assert.notEqual(cycleReasonLabel(code, 'en'), code);
  }
  assert.equal(cycleReasonLabel('future_reason'), 'Причина не распознана');
  assert.equal(cycleReasonLabel('Manual correction'), 'Manual correction');
  assert.equal(cycleReasonLabel('Исправлено администратором'), 'Исправлено администратором');
  assert.equal(cycleReasonLabel(null), '-');
});

test('source and reinforcement rejection reasons have specific player-facing translations', () => {
  for (const code of ['not_ranked', 'unsupported_patch', 'missing_match_times', 'invalid_match_times',
    'too_short', 'outside_battle_window', 'reinforcement_blocked', 'reinforcement_not_arrived', 'interception_pending']) {
    assert.notEqual(cycleReasonLabel(code), 'Причина не распознана', code);
    assert.notEqual(cycleReasonLabel(code, 'en'), 'Unrecognized reason', code);
  }
});

test('membership rejection explains cycle exclusion even after the player rejoins', () => {
  assert.match(cycleReasonLabel('membership_changed'), /этом цикле/);
  assert.match(cycleReasonLabel('membership_changed', 'en'), /this cycle/);
});

test('review checkbox follows server state and discards a draft from an older state', () => {
  assert.equal(reviewCounted({ counted: true }, null), true);
  assert.equal(reviewCounted({ counted: false }, null), false);
  const draft = { original: true, value: false };
  assert.equal(reviewCounted({ counted: true }, draft), false);
  assert.equal(reviewCounted({ counted: false }, draft), false);
  assert.equal(reviewCounted({ counted: true }, { original: false, value: false }), true);
});

test('groups every independent side without inventing a cycle winner', () => {
  const battles = [{ id: 1, sides: [1, 2, 3].map(clan_id => ({ clan_id, score: '-0.125', members: [] })) },
    { id: 2, sides: [{ clan_id: 3, clan_name: 'Third', score: '0.025', members: [] }] }];
  const groups = groupClanBattles(battles);
  assert.equal(groups.length, 3);
  assert.equal(groups[2].battles.length, 2);
  assert.equal(groups[2].score, '-0.1');
  assert.equal(groups[2].clan_name, 'Third');
  assert.equal('winner' in groups[2], false);
  assert.deepEqual(groupClanBattles([]), []);
});

test('formats negative and tiny decimal scores without rounding away points', () => {
  assert.equal(formatScore('-0.000000000001'), '-0.000000000001');
  assert.equal(formatScore('12.5000'), '12.5');
  assert.equal(formatScore('0'), '0');
  assert.equal(formatScore(null), '-');
  assert.equal(formatScore('0E-12'), '0');
  assert.equal(formatScore('1E-12'), '0.000000000001');
  assert.equal(formatScore('-1.25E+3'), '-1250');
  assert.equal(groupClanBattles([{ sides: [{ clan_id: 1, score: '0E-12' }] }])[0].score, '0');
});

test('groups replay contributions retaining each player and both reasons', () => {
  const rows = [{ replay_id: 'r', user_id: 1, reason: 'rule', review_reason: 'admin' },
    { replay_id: 'r', user_id: 2 }, { replay_id: 'other', user_id: 3 }];
  const groups = groupContributions(rows);
  assert.equal(groups.length, 2);
  assert.deepEqual(groups[0].contributions, rows.slice(0, 2));
});

test('adjustment command persists across logical retries but changes for changed payload or success', () => {
  let n = 0;
  const command = createAdjustmentCommand(() => `id-${++n}`);
  const payload = { clan_id: 1, amount: '-1.25', reason: 'Correction' };
  assert.equal(command.get(payload), command.get({ ...payload }));
  assert.notEqual(command.get(payload), command.get({ ...payload, reason: 'Other' }));
  const previous = command.get(payload);
  command.reset();
  assert.notEqual(previous, command.get(payload));
});

test('ownership command follows target and preview while identical retries keep their ID', () => {
  let n = 0;
  const command = createAdjustmentCommand(() => `ownership-${++n}`);
  const original = { new_owner_clan_id: 1, preview_token: 'old', reason: 'Correction' };
  const first = command.get(original);
  assert.equal(command.get({ reason: 'Correction', preview_token: 'old', new_owner_clan_id: 1 }), first);
  assert.notEqual(command.get({ ...original, new_owner_clan_id: 2 }), first);
  const second = command.get(original);
  assert.notEqual(command.get({ ...original, preview_token: 'new' }), second);
});
