import test from 'node:test';
import assert from 'node:assert/strict';
import { archiveEndpoint, archiveMapUrl, archiveAwardUrl, archiveViewBox, archiveClans, archiveClanColor, isArchiveInterseason } from './seasonArchive.js';
import { resolveCampaignNavigation } from './campaignNavigation.js';

test('archive endpoints only accept positive integer IDs', () => {
  assert.equal(archiveEndpoint(), '/api/v1/campaign/archives');
  assert.equal(archiveEndpoint('1'), '/api/v1/campaign/archives/1');
  for (const id of ['../clans', '1?secret', '0', '-1', '1.5', '//host', '9007199254740992']) {
    assert.throws(() => archiveEndpoint(id));
  }
});

test('backdrop and awards accept only their internal immutable asset paths', () => {
  assert.equal(archiveMapUrl('/api/v1/campaign/archives/1/map.svg', 1), '/api/v1/campaign/archives/1/map.svg');
  for (const url of ['/map.svg', '/api/v1/campaign/archives/2/map.svg', 'https://other/map.svg', 'javascript:alert(1)', '//host/map.svg']) {
    assert.equal(archiveMapUrl(url, 1), null);
  }
  assert.equal(archiveAwardUrl('/assets/awards/clan/season-champion.png'), '/assets/awards/clan/season-champion.png');
  assert.equal(archiveAwardUrl('/assets/awards/clan/../../secret.svg'), null);
});

test('frozen viewBox including origin is retained; invalid geometry fails closed', () => {
  assert.deepEqual(archiveViewBox('10 -20 3570.6 2339.7'), { x: 10, y: -20, width: 3570.6, height: 2339.7 });
  for (const input of ['', '0 0 0 10', '0 0 NaN 10', '0 0 -1 10', '0 0 10 10 20']) assert.throws(() => archiveViewBox(input));
});

test('standings use frozen rank, names, colors and awards without recalculation or mutation', () => {
  const awards = Object.freeze([{ key: 'winner', label_key: 'clan_award_season_champion' }]);
  const second = Object.freeze({ clan_id: 2, clan_name: 'Old name', clan_map_color: '#12abef', rank: 2, influence: 9999, awards });
  const first = Object.freeze({ clan_id: 1, rank: 1, influence: 1, awards: [] });
  const clans = Object.freeze([second, first]);
  assert.deepEqual(archiveClans(clans), [first, second]);
  assert.equal(archiveClans(clans)[1], second);
  assert.equal(archiveClanColor(second), '#12abef');
  assert.equal(archiveClanColor({ clan_map_color: 'url(https://other)' }), '#89938b');
});

test('interseason recognizes both navigation contracts without treating a missing season as completed', () => {
  assert.equal(isArchiveInterseason({ mode: 'interseason' }), true);
  assert.equal(isArchiveInterseason({ mode: 'legacy', interseason: true }), true);
  assert.equal(isArchiveInterseason({ mode: 'legacy' }), false);
  assert.equal(isArchiveInterseason(null), false);
});

test('completed legacy navigation resolves to the exact public archive contract', () => {
  const navigation = resolveCampaignNavigation({ mechanics_version: 'legacy', cycle: null,
    interseason: true, archived_season_id: 1, territory_battles: [] });
  assert.deepEqual(navigation, { mode: 'interseason', interseason: true, archivedSeasonId: 1,
    href: '/seasons', territoryBattles: [] });
  assert.equal(isArchiveInterseason(navigation), true);
});
