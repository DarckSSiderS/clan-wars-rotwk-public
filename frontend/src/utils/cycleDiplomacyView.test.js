import test from 'node:test';
import assert from 'node:assert/strict';
import { diplomacyMessage, diplomacyLabel, isDiplomacyHead, diplomacyEditable,
  parseWarDuration, filterRelations, relationForClan, pairRevision, buildDiplomacyAction } from './cycleDiplomacyView.js';

test('head rights use the actual clan response and never roles or absent IDs', () => {
  assert.equal(isDiplomacyHead({ id: 7 }, { id: 1, leader_id: 7 }), true);
  assert.equal(isDiplomacyHead({ id: 8, is_warlord: true }, { id: 1, leader_id: 7 }), false);
  assert.equal(isDiplomacyHead({}, {}), false);
  assert.equal(isDiplomacyHead({ id: 7 }, null), false);
});

test('only preparation and rest allow management', () => {
  for (const phase of ['registration', 'battle', 'replay_loading', 'settlement', 'complete', 'season_ended', undefined]) {
    assert.equal(diplomacyEditable(phase), false);
  }
  assert.equal(diplomacyEditable('preparation'), true);
  assert.equal(diplomacyEditable('rest'), true);
});

test('duration is a positive integer without precision loss or an invented maximum', () => {
  for (const value of ['', ' ', '0', '-1', '1.2', '1e3', '+1', 'Infinity']) {
    assert.throws(() => parseWarDuration(value, false));
  }
  assert.equal(parseWarDuration(' 002 ', false), '2');
  assert.equal(parseWarDuration('999999999999999999999999999999', false), '999999999999999999999999999999');
  assert.equal(parseWarDuration('', true), null);
});

const relations = [
  { clan_low_id: 1, clan_high_id: 2, clan_low: { name: 'Лес' }, clan_high: { name: 'Moon' }, status: 'hostile' },
  { clan_low_id: 2, clan_high_id: 3, clan_low: { name: 'Moon' }, clan_high: { name: 'Sun' }, status: 'allied' },
];
test('public filters search current names and never merge private data', () => {
  assert.deepEqual(filterRelations(relations, ' moon ', 'allied'), [relations[1]]);
  assert.deepEqual(filterRelations(relations, 'ЛЕС', 'all'), [relations[0]]);
  assert.deepEqual(filterRelations(relations, 'old name', 'all'), []);
  assert.equal(relationForClan(relations, 2, 1), relations[0]);
  assert.equal(relationForClan(relations, 1, 3), null);
  assert.equal(relations.length, 2);
});

test('private revisions and exact action payloads are bounded to the selected pair', () => {
  const own = { pairs: [{ other_clan_id: 2, revision: 6 }], proposals: [{ id: 4 }] };
  assert.equal(pairRevision(own, 2), 6);
  assert.equal(pairRevision(own, 3), 0);
  assert.deepEqual(buildDiplomacyAction({ action: 'declare_war', otherClanId: 2, own, duration: '3' }),
    { action: 'declare_war', other_clan_id: 2, expected_revision: 6, duration: '3' });
  assert.deepEqual(buildDiplomacyAction({ action: 'accept', otherClanId: 2, own, proposalId: 4 }),
    { action: 'accept', other_clan_id: 2, expected_revision: 6, proposal_id: 4 });
  assert.throws(() => buildDiplomacyAction({ action: 'unknown', otherClanId: 2, own }));
  assert.throws(() => buildDiplomacyAction({ action: 'accept', otherClanId: 2, own }));
  assert.throws(() => buildDiplomacyAction({ action: 'declare_war', otherClanId: 0, own, duration: '1' }));
});

test('all public statuses, proposal kinds and sources have RU/EN labels without raw codes', () => {
  for (const key of ['allied', 'hostile', 'neutral', 'pending', 'accepted', 'revoked', 'expired', 'alliance', 'peace', 'attack', 'declaration']) {
    assert.notEqual(diplomacyLabel(key, 'ru'), key);
    assert.notEqual(diplomacyLabel(key, 'en'), key);
  }
  assert.equal(diplomacyMessage('diplomacy_title', 'en-GB'), 'Diplomacy');
  assert.equal(diplomacyMessage('diplomacy_title'), 'Дипломатия');
  assert.equal(diplomacyLabel('future_code', 'en'), 'Unavailable');
});
