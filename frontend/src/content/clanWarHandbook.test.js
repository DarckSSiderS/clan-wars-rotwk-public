import assert from 'node:assert/strict';
import test from 'node:test';
import { CLAN_WAR_HANDBOOK_SECTION_IDS, getClanWarHandbook } from './clanWarHandbook.js';

const EXPECTED_SECTION_IDS = [
  'overview', 'site-guide', 'getting-started', 'clan-roles', 'territories', 'attacks',
  'matches', 'war-result', 'economy', 'relics', 'market', 'progress', 'fairplay', 'faq',
];

const collectText = (value) => {
  if (typeof value === 'string') return value;
  if (Array.isArray(value)) return value.map(collectText).join(' ');
  if (value && typeof value === 'object') return Object.values(value).map(collectText).join(' ');
  return '';
};

test('handbook is organized as a complete player guide', () => {
  assert.deepEqual(CLAN_WAR_HANDBOOK_SECTION_IDS, EXPECTED_SECTION_IDS);
  for (const language of ['ru', 'en', 'de']) {
    const handbook = getClanWarHandbook(language);
    assert.deepEqual(handbook.categories.map(({ id }) => id), EXPECTED_SECTION_IDS);
    assert.ok(handbook.categories.every((category) => category.summary));
  }
});

test('public handbook does not expose implementation terminology', () => {
  const forbidden = /\b(?:api|backend|ledger|worker|snapshot|operation_id|uuid|idempotent)\b|атомар|идемпотент|транзакц/iu;
  for (const language of ['ru', 'en', 'de']) {
    assert.doesNotMatch(collectText(getClanWarHandbook(language)), forbidden, language);
  }
});

test('handbook describes the one-minute threshold in every language', () => {
  for (const [language, expected] of [['ru', /1 минуты/], ['en', /1 minute/], ['de', /1 Minute/]]) {
    const text = collectText(getClanWarHandbook(language));
    assert.match(text, expected);
    assert.doesNotMatch(text, /2 минут|2 minutes|2 Minuten/);
  }
});

const interseason = {
  mechanics_version: null,
  season: null,
  rule_set: { version: 5, values: { WAR_DURATION_HOURS: 60 } },
  guide: { mechanics_version: 'cycle_v1', status: 'upcoming', previous_season_id: 1 },
};
const textOf = value => JSON.stringify(value);

test('default interseason shows upcoming cycle rules with an honest first section', () => {
  const before = structuredClone(interseason);
  for (const language of ['ru', 'en', 'de']) {
    const guide = getClanWarHandbook(language, interseason);
    assert.match(guide.title, /циклов/);
    assert.equal(guide.categories[0].id, 'overview');
    assert.match(guide.categories[0].title, /Межсезонье: новый сезон ещё не запущен/);
    assert.match(guide.intro, /после запуска нового сезона/);
    assert.match(guide.sectionMeta, /после запуска/);
    assert.doesNotMatch(guide.sectionMeta, /Сезон 2|v5|60/);
    const overview = textOf(guide.categories[0]);
    assert.match(overview, /профил|статистик/);
    assert.match(overview, /доход[^.]*не начисляется/);
    assert.match(overview, /принятые[^.]*караван/iu);
    assert.ok(overview.includes('/seasons/1'));
    assert.ok(overview.includes('/rules?season=1'));
    assert.match(textOf(guide), /72 часа|48 часов/);
  }
  assert.deepEqual(interseason, before);
});

test('upcoming guide cannot override explicit history, errors or incomplete context', () => {
  const historical = { mechanics_version: null, season: { id: 1, name: 'Первый сезон' }, rule_set: interseason.rule_set };
  const legacy = getClanWarHandbook('ru', historical, { seasonId: '1' });
  assert.deepEqual(getClanWarHandbook('ru', { ...historical, guide: interseason.guide }, { seasonId: '1' }), legacy);
  for (const options of [{ seasonId: '1' }, { seasonId: '2' }, { loading: true }, { loadError: true }]) {
    assert.doesNotMatch(getClanWarHandbook('ru', interseason, options).title, /циклов/);
  }
  for (const guide of [undefined, {}, { ...interseason.guide, status: 'active' },
    { ...interseason.guide, mechanics_version: 'cycle_v2' },
    { ...interseason.guide, previous_season_id: null },
    { ...interseason.guide, previous_season_id: -1 }]) {
    assert.doesNotMatch(getClanWarHandbook('ru', { ...interseason, guide }).title, /циклов/);
  }
});

test('active and historical cycle seasons keep their own season context', () => {
  const active = { mechanics_version: 'cycle_v1', season: { id: 2, name: 'Настоящий сезон', status: 'active' } };
  for (const options of [{}, { seasonId: '2' }]) {
    const guide = getClanWarHandbook('ru', { ...active, guide: interseason.guide }, options);
    assert.equal(guide.seasonLabel, 'Настоящий сезон');
    assert.doesNotMatch(textOf(guide.categories[0]), /Межсезонье/);
  }
});

test('upcoming guide keeps cycle section ids and feedback backlinks', () => {
  const active = getClanWarHandbook('ru', { mechanics_version: 'cycle_v1', season: { id: 2 } });
  const upcoming = getClanWarHandbook('ru', interseason);
  assert.deepEqual(upcoming.categories.map(({ id }) => id), active.categories.map(({ id }) => id));
  assert.ok(textOf(upcoming).includes('/feedback?from=%2Frules%3Fsection%3Dfairplay'));
  for (const id of CLAN_WAR_HANDBOOK_SECTION_IDS) {
    assert.ok(upcoming.categories.some(category => category.id === id || category.aliases?.includes(id)), id);
  }
});
