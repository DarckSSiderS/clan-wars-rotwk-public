export function nextCycleDeadline(cycle) {
  const field = {
    scheduled: 'starts_at', registration: 'preparation_at', preparation: 'battle_at',
    battle: 'battle_ends_at', replay_loading: 'replay_deadline',
    rest: 'next_cycle_starts_at', complete: 'settled_at', season_ended: 'settled_at',
  }[cycle?.phase];
  return field && cycle[field] ? { key: `cycle_${field}`, value: cycle[field] } : null;
}

export function cycleSchedule(cycle) {
  const fields = ['starts_at', 'preparation_at', 'battle_at', 'battle_ends_at', 'replay_deadline', 'settled_at'];
  const index = { scheduled: 0, registration: 0, preparation: 1, battle: 2,
    replay_loading: 3, settlement: 5, rest: 5, complete: 5, season_ended: 5 }[cycle.phase] ?? 0;
  const steps = fields.slice(index).flatMap((field, offset) => {
    if (field === 'starts_at' && (!cycle.starts_at || cycle.starts_at === cycle.preparation_at)) return [];
    if (field !== 'settled_at' && !cycle[field]) return [];
    return [{
      key: cycle.phase === 'rest' && field === 'settled_at' ? 'cycle_rest_started_at'
        : cycle.phase === 'replay_loading' && field === 'battle_ends_at' ? 'cycle_replay_loading_started_at'
          : `cycle_${field}`,
      value: cycle[field] ?? null,
      current: offset === 0 && !['scheduled', 'complete', 'season_ended'].includes(cycle.phase),
    }];
  });
  if (!cycle.season_end_requested && cycle.phase !== 'season_ended') {
    steps.push({ key: 'cycle_next_cycle_starts_at', value: cycle.next_cycle_starts_at ?? null, next: true });
  }
  return steps;
}

export function filterBattleList(battles, status = 'all', query = '') {
  const search = query.trim().toLocaleLowerCase();
  return battles.filter(battle => (
    (status === 'all' || Boolean(battle.completed_at) === (status === 'completed'))
    && (!search || [battle.territory_name, ...(battle.sides || []).map(side => side.clan_name)]
      .join(' ').toLocaleLowerCase().includes(search))
  ));
}

export function summarizeClanBattles(battles, clanId) {
  return battles.reduce((result, battle) => {
    const side = battle.sides?.find(row => String(row.clan_id) === String(clanId));
    if (!side) return result;
    result.total++;
    result.active += Number(!battle.completed_at);
    result.won += Number(Boolean(battle.completed_at) && String(battle.winner_clan_id) === String(clanId));
    result.attacks += Number(side.role === 'attack');
    result.defenses += Number(side.role === 'defense');
    return result;
  }, { total: 0, active: 0, won: 0, attacks: 0, defenses: 0 });
}
