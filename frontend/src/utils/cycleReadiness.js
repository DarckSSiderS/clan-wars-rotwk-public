export function cycleReadiness(planning, preparation, economy) {
  if (!planning?.snapshot_ready) return null;
  const eligible = new Set((planning.members || []).filter(row => row.eligible && !row.scouting).map(row => row.user_id));
  const orders = (planning.plan?.orders || []).filter(row => eligible.has(row.user_id));
  const assigned = new Set(orders.map(row => row.user_id));
  const targets = new Set(planning.defence_targets || []);
  for (const row of planning.defence_template?.fallback_orders || []) {
    if (row.kind === 'defend' && eligible.has(row.user_id) && !assigned.has(row.user_id) && targets.has(row.territory_id)) {
      orders.push(row);
      assigned.add(row.user_id);
    }
  }
  const defended = new Set(orders.filter(row => row.kind === 'defend').map(row => row.territory_id));
  const request = preparation?.scout?.request;
  return {
    free: [...eligible].filter(id => !assigned.has(id)).length,
    uncovered: (planning.defence_targets || []).filter(id => !defended.has(id)).length,
    reserve: new Set(orders.filter(row => row.kind === 'reserve').map(row => row.user_id)).size,
    scout: !preparation?.scout ? null : !request ? 'none' : request.scout_user_id ? 'assigned' : 'unassigned',
    relics: economy?.state ? economy.state.active_relics?.length ?? 0 : null,
  };
}

const messages = {
  screen: ['Готовность клана', 'Clan readiness'], free: ['Свободные игроки', 'Free players'],
  uncovered: ['Неприкрытые земли', 'Uncovered territories'], reserve: ['Запас', 'Reserves'],
  scout: ['Разведчик', 'Scout'], relics: ['Активные реликвии', 'Active relics'],
  assigned: ['Назначен', 'Assigned'], unassigned: ['Без игрока', 'No player assigned'], none: ['Не назначен', 'Not assigned'],
  unavailable: ['Сведения о готовности недоступны', 'Readiness is unavailable'],
  refreshFailed: ['Не удалось обновить сведения. Показаны последние загруженные данные.', 'Refresh failed. Showing the last loaded data.'],
};
export const readinessMessage = (key, language) => (messages[key] || messages.unavailable)[String(language).startsWith('en') ? 1 : 0];
