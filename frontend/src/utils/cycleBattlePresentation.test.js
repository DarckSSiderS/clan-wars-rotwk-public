import { test } from 'node:test';
import assert from 'node:assert/strict';
import * as presentation from './cycleBattlePresentation.js';
const { nextCycleDeadline, filterBattleList, summarizeClanBattles } = presentation;

test('обзор показывает ближайший срок этапа, а не все даты подряд', () => {
  const dates = { phase: 'preparation', battle_at: '2026-10-25T10:00:00Z', battle_ends_at: '2026-10-27T10:00:00Z', replay_deadline: '2026-10-27T10:05:00Z', settled_at: '2026-10-27T10:10:00Z' };
  assert.deepEqual(nextCycleDeadline(dates), { key: 'cycle_battle_at', value: dates.battle_at });
  assert.equal(nextCycleDeadline({ ...dates, phase: 'battle' }).value, dates.battle_ends_at);
  assert.equal(nextCycleDeadline({ ...dates, phase: 'replay_loading' }).value, dates.replay_deadline);
  assert.equal(nextCycleDeadline({ ...dates, phase: 'complete' }).value, dates.settled_at);
  assert.equal(nextCycleDeadline({ phase: 'preparation' }), null);
});

test('расписание сдвигается к текущему этапу, после итогов показывает точный старт', () => {
  const cycle = { phase: 'preparation', starts_at: 'start', preparation_at: 'prep', battle_at: 'battle',
    battle_ends_at: 'end', replay_deadline: 'replays', settled_at: null, next_cycle_starts_at: null };
  const steps = phase => presentation.cycleSchedule({ ...cycle, phase });
  assert.deepEqual(steps('preparation').map(row => row.key), [
    'cycle_preparation_at', 'cycle_battle_at', 'cycle_battle_ends_at', 'cycle_replay_deadline',
    'cycle_settled_at', 'cycle_next_cycle_starts_at',
  ]);
  assert.equal(steps('preparation')[0].current, true);
  assert.equal(steps('settlement').length, 2);
  const rest = { ...cycle, phase: 'rest', settled_at: 'results', next_cycle_starts_at: 'next' };
  assert.deepEqual(nextCycleDeadline(rest), { key: 'cycle_next_cycle_starts_at', value: 'next' });
  assert.deepEqual(presentation.cycleSchedule(rest).map(row => [row.key, row.value]), [
    ['cycle_rest_started_at', 'results'], ['cycle_next_cycle_starts_at', 'next'],
  ]);
  assert.equal(presentation.cycleSchedule({ ...rest, phase: 'season_ended', season_end_requested: true }).length, 1);
  assert.equal(steps('registration').at(-1).value, null);
  assert.equal(presentation.cycleSchedule({ ...cycle, phase: 'scheduled', starts_at: 'prep' })
    .filter(row => row.value === 'prep').length, 1);
});

const battles = [
  { id: 1, territory_name: 'Арнор', completed_at: null, sides: [{ clan_id: 10, clan_name: 'Север', role: 'attack' }] },
  { id: 2, territory_name: 'Рохан', completed_at: '2026-10-24', winner_clan_id: 10, sides: [{ clan_id: 10, clan_name: 'Север', role: 'defense' }] },
  { id: 3, territory_name: 'Гондор', completed_at: '2026-10-24', winner_clan_id: 20, sides: [{ clan_id: 20, clan_name: 'Юг', role: 'attack' }] },
];
test('фильтры и поиск не теряют стороны многостороннего боя', () => {
  assert.deepEqual(filterBattleList(battles, 'active', '').map(row => row.id), [1]);
  assert.deepEqual(filterBattleList(battles, 'completed', 'сЕВ').map(row => row.id), [2]);
  assert.deepEqual(filterBattleList(battles, 'all', ' гондор ').map(row => row.id), [3]);
  assert.equal(filterBattleList(battles, 'all', '').length, 3);
});
test('сводка клана учитывает только его участие без изменения исходных данных', () => {
  assert.deepEqual(summarizeClanBattles(battles, '10'), { total: 2, active: 1, won: 1, attacks: 1, defenses: 1 });
  assert.equal(battles[0].sides.length, 1);
});
