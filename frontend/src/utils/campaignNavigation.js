const positiveId = value => Number.isSafeInteger(value) && value > 0;

export function resolveCampaignNavigation(data) {
  if (!data || !['legacy', 'cycle_v1'].includes(data.mechanics_version)
      || !Array.isArray(data.territory_battles)) throw new Error('Invalid campaign navigation response');
  if (data.interseason === true) {
    if (!positiveId(data.archived_season_id)) throw new Error('Invalid archived season');
    return { mode: 'interseason', interseason: true, archivedSeasonId: data.archived_season_id,
      href: '/seasons', territoryBattles: [] };
  }
  if (data.mechanics_version === 'legacy') return { mode: 'legacy', href: null, territoryBattles: [] };
  if (data.cycle === null) return { mode: 'cycle_v1', href: null, territoryBattles: [] };
  if (!positiveId(data.cycle?.id) || data.territory_battles.some(row => !positiveId(row?.battle_id) || !positiveId(row?.territory_id))) {
    throw new Error('Invalid current cycle or territory battle');
  }
  const href = `/campaign/cycles/${data.cycle.id}`;
  return { mode: 'cycle_v1', cycleId: data.cycle.id, cycle: data.cycle, href,
    diplomacyHref: `${href}/diplomacy`, territoryBattles: data.territory_battles };
}

export function campaignTerritoryBattle(navigation, territoryId) {
  if (navigation?.mode !== 'cycle_v1' || !navigation.href) return null;
  const row = navigation.territoryBattles.find(battle => String(battle.territory_id) === String(territoryId));
  return row ? { battle_id: row.battle_id, href: `${navigation.href}?territory=${row.territory_id}` } : null;
}
