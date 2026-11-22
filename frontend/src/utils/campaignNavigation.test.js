import test from 'node:test';
import assert from 'node:assert/strict';
import { resolveCampaignNavigation, campaignTerritoryBattle } from './campaignNavigation.js';

test('cycle navigation exposes one overview and a territory-specific battle link', () => {
  const navigation = resolveCampaignNavigation({ mechanics_version: 'cycle_v1',
    cycle: { id: 7 }, territory_battles: [{ battle_id: 66, territory_id: 12 }] });
  assert.equal(navigation.href, '/campaign/cycles/7');
  assert.equal(navigation.diplomacyHref, '/campaign/cycles/7/diplomacy');
  assert.deepEqual(campaignTerritoryBattle(navigation, 12), {
    battle_id: 66, href: '/campaign/cycles/7?territory=12',
  });
  assert.equal(campaignTerritoryBattle(navigation, 13), null);
});

test('legacy and uninitialized cycles stay separate', () => {
  const legacy = resolveCampaignNavigation({ mechanics_version: 'legacy', cycle: null, territory_battles: [] });
  assert.equal(legacy.mode, 'legacy');
  assert.equal(legacy.href, null);
  assert.equal(campaignTerritoryBattle(legacy, 12), null);
  const pending = resolveCampaignNavigation({ mechanics_version: 'cycle_v1', cycle: null, territory_battles: [] });
  assert.equal(pending.mode, 'cycle_v1');
  assert.equal(pending.href, null);
});

test('invalid campaign responses cannot silently select legacy mode or form invalid URLs', () => {
  for (const data of [null, {}, { mechanics_version: 'other' },
    { mechanics_version: 'cycle_v1', cycle: { id: '../1' }, territory_battles: [] },
    { mechanics_version: 'cycle_v1', cycle: { id: 0 }, territory_battles: [] },
    { mechanics_version: 'cycle_v1', cycle: { id: 1 }, territory_battles: [{ territory_id: 1 }] }]) {
    assert.throws(() => resolveCampaignNavigation(data));
  }
});

for (const mechanics of ['legacy', 'cycle_v1']) {
  test(`${mechanics} interseason explicitly preserves the archive without battle links`, () => {
    const navigation = resolveCampaignNavigation({ mechanics_version: mechanics,
      interseason: true, archived_season_id: 1, cycle: { id: 7 },
      territory_battles: [{ battle_id: 66, territory_id: 12 }] });
    assert.deepEqual(navigation, { mode: 'interseason', interseason: true,
      archivedSeasonId: 1, href: '/seasons', territoryBattles: [] });
    assert.equal(campaignTerritoryBattle(navigation, 12), null);
  });
}

test('explicit false keeps existing legacy behavior and malformed interseason is rejected', () => {
  const navigation = resolveCampaignNavigation({ mechanics_version: 'legacy',
    interseason: false, cycle: null, territory_battles: [] });
  assert.equal(navigation.mode, 'legacy');
  for (const archived_season_id of [undefined, null, 0, '../1']) {
    assert.throws(() => resolveCampaignNavigation({ mechanics_version: 'legacy',
      interseason: true, archived_season_id, cycle: null, territory_battles: [] }));
  }
});
