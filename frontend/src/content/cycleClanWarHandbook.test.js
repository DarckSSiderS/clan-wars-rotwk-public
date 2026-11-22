import assert from 'node:assert/strict';
import test from 'node:test';
import { getClanWarHandbook } from './clanWarHandbook.js';

const confirmed = {
  mechanics_version: 'cycle_v1',
  season: { id: 12, name: 'Война за Север' },
  rule_set: { version: 7, values: { WAR_DURATION_HOURS: 60 } },
};
const textOf = (handbook) => JSON.stringify(handbook);

test('guide explains dispatch origin without exposing administrative repair details', () => {
  const guide = textOf(getClanWarHandbook('ru', confirmed));
  assert.match(guide, /землю отправления/);
  assert.match(guide, /без владений/);
  assert.doesNotMatch(guide, /исправлен|переписыван|откат/iu);
});

test('scout occupies one verified player for the cycle and cannot be replaced', () => {
  const guide = getClanWarHandbook('ru', confirmed);
  const text = textOf(guide.categories.find(({ id }) => id === 'scouting'));
  assert.match(text, /одного свободного участника/);
  assert.match(text, /разведчик[^.]*весь цикл/iu);
  assert.match(text, /нельзя[^.]*отряд[^.]*запас[^.]*засад/iu);
  assert.match(text, /цель и разведчика[^.]*нельзя/);
});

test('defence template supplements only free players and never creates attacks', () => {
  const guide = getClanWarHandbook('ru', confirmed);
  const text = textOf(guide.categories.find(({ id }) => id === 'attacks'));
  assert.match(text, /Защитный шаблон/);
  assert.match(text, /отдых[^.]*подготовк/iu);
  assert.match(text, /ручные приказы имеют приоритет/iu);
  assert.match(text, /разведчик/iu);
  assert.match(text, /вышедш[^.]*потерян/iu);
  assert.match(text, /автоматических атак нет/iu);
  assert.match(text, /без шаблона[^.]*защит/iu);
});

test('cycle rules avoid technical and unlaunched feature promises', () => {
  const text = textOf(getClanWarHandbook('ru', confirmed));
  assert.doesNotMatch(text, /UUID|revision|command_id|\bDB\b|исправлен|календар|90[- ]|персональн[^.]*реликв|снимок|актуальной версии/iu);
  assert.match(text, /четырёх/);
  assert.match(text, /−50/);
  assert.match(text, /10%[^.]*получаемого груза/);
  assert.match(text, /Золото нельзя передать/);
});

test('only confirmed cycle mode of the selected season selects the Russian cycle guide', () => {
  for (const language of ['ru', 'en', 'de']) {
    const guide = getClanWarHandbook(language, confirmed, { seasonId: '12' });
    assert.match(guide.title, /циклов/);
    assert.equal(guide.seasonLabel, 'Война за Север');
    assert.match(textOf(guide), /исторический Elo/);
    assert.doesNotMatch(textOf(guide), /60 часов|очк[аои] атаки|48-часов[а-я]* (?:замок|запрет)|48 часов[^.!?]*активац/);
  }
});

test('missing, unknown, nested or stale modes cannot activate cycle rules', () => {
  const legacy = getClanWarHandbook('ru', { season: confirmed.season, rule_set: confirmed.rule_set });
  for (const payload of [
    {},
    { ...confirmed, mechanics_version: undefined },
    { ...confirmed, mechanics_version: 'cycle_v2' },
    { ...confirmed, mechanics_version: 'legacy' },
    { ...confirmed, mechanics_version: undefined, season: { ...confirmed.season, mechanics_version: 'cycle_v1' } },
    { ...confirmed, mechanics_version: undefined, rule_set: { ...confirmed.rule_set, mechanics_version: 'cycle_v1' } },
    { ...confirmed, season: null },
  ]) {
    assert.doesNotMatch(getClanWarHandbook('ru', payload).title, /циклов/);
  }
  assert.deepEqual(getClanWarHandbook('ru', { ...confirmed, mechanics_version: 'legacy' }), legacy);
  for (const options of [{ seasonId: '13' }, { loading: true }, { loadError: true }]) {
    assert.doesNotMatch(getClanWarHandbook('ru', confirmed, options).title, /циклов/);
  }
});

test('cycle guide has unique navigable sections and explains scoring and timing without legacy promises', () => {
  const guide = getClanWarHandbook('ru', confirmed);
  const ids = guide.categories.map(({ id }) => id);
  assert.equal(new Set(ids).size, ids.length);
  for (const id of ['overview', 'attacks', 'matches', 'war-result', 'reserve', 'interception', 'diplomacy', 'scouting', 'economy', 'relics', 'market', 'upgrades']) {
    assert.ok(ids.includes(id), id);
  }
  for (const category of guide.categories) {
    assert.ok(category.title && category.summary && category.sections.length);
  }
  const text = textOf(guide);
  for (const pattern of [/72 часа/, /24 часа/, /48 часов/, /5 минут/, /12 часов/, /100 \+ d\/8/, /−50 \+ d\/16/, /N\+3/, /0,5/, /без золота/, /200 золота/]) {
    assert.match(text, pattern);
  }
  assert.doesNotMatch(text, /\b(?:API|backend|snapshot|UUID|worker|ledger)\b|идемпотент|транзакц/iu);
});
