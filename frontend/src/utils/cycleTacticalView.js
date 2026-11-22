import { assignPlayer, routeKey } from './cyclePlanningView.js';

export function squadGroups(orders) {
  const groups = new Map();
  for (const order of orders) {
    const key = `${order.kind}:${routeKey(order)}`;
    if (!groups.has(key)) groups.set(key, { ...order, key, user_ids: [] });
    groups.get(key).user_ids.push(order.user_id);
  }
  return [...groups.values()];
}

export function assignSquad(orders, userIds, order) {
  return [...new Set(userIds)].reduce((rows, id) => assignPlayer(rows, id, order), orders);
}

export function battleStatus(battle) {
  if (battle.completed) return 'completed';
  if (battle.status) return battle.status;
  const attackers = (battle.sides || []).filter(side => side.clan_id !== battle.owner_clan_id);
  return battle.owner_clan_id == null ? (attackers.length > 1 ? 'contested' : 'neutral_claim')
    : attackers.length ? 'contested' : 'defense';
}

export function attackDrawing(route, boxes) {
  const source = boxes.get(route.source_territory_id), target = boxes.get(route.target_territory_id);
  if (!source || !target || route.source_territory_id === route.target_territory_id) return null;
  const a = [source.x + source.width / 2, source.y + source.height / 2];
  const b = [target.x + target.width / 2, target.y + target.height / 2];
  const dx = b[0] - a[0], dy = b[1] - a[1], distance = Math.hypot(dx, dy);
  if (distance < 1) return null;
  const inset = Math.min(48, distance / 4), ux = dx / distance, uy = dy / distance;
  return { start: [a[0] + ux * inset, a[1] + uy * inset], end: [b[0] - ux * inset, b[1] - uy * inset],
    middle: [(a[0] + b[0]) / 2, (a[1] + b[1]) / 2], angle: Math.atan2(dy, dx) * 180 / Math.PI };
}

export function visibleHelpRequests(data) {
  if (data?.phase !== 'battle' || !(Date.parse(data.server_time) < Date.parse(data.command_deadline))) return [];
  return data.requests || [];
}

export function placeMapLabel(anchor, text, occupied) {
  const width = Math.max(80, text.length * 27), height = 64;
  const offsets = [[0, -22], [0, 92], [0, -140], [0, 200], [-240, -80], [240, 120], [-240, 180], [240, -200]];
  for (let step = 0; ; step += 1) {
    const [dx, dy] = offsets[step] || [0, -220 - (step - offsets.length) * 90];
    const point = { x: anchor[0] + dx, y: anchor[1] + dy };
    const box = { x: point.x - width / 2 - 10, y: point.y - height + 8, width: width + 20, height };
    if (occupied.some(other => box.x < other.x + other.width && box.x + box.width > other.x && box.y < other.y + other.height && box.y + box.height > other.y)) continue;
    occupied.push(box);
    return point;
  }
}

const messages = {
  contested: ['Битва за территорию', 'Territory battle'], defense: ['Оборона · атак нет', 'Defence · no attacks'],
  neutral_claim: ['Занятие нейтральной земли', 'Neutral land claim'], completed: ['Битва завершена', 'Battle settled'],
  owner: ['Владелец', 'Owner'], neutral: ['Нейтральная земля', 'Neutral land'],
  defender: ['Оборона', 'Defence'], attacker: ['Атака', 'Attack'], players: ['Игроков', 'Players'],
  openBattle: ['Открыть сражение', 'Open battle'], help: ['Нужна помощь', 'Help requested'],
  moving: ['Подкрепление в пути', 'Reinforcements en route'],
  preparation: ['Подготовка · приказы кланов ещё скрыты', 'Preparation · clan orders are still hidden'],
  roster: ['Игроки клана', 'Clan players'], squads: ['Отряды и назначения', 'Squads and assignments'],
  selected: ['Выбрано', 'Selected'], apply: ['Назначить выбранных', 'Assign selected'],
  squadAssignment: ['Назначение отряда', 'Squad assignment'],
  remove: ['Снять назначение', 'Remove assignment'], select: ['Выбрать игрока', 'Select player'],
  selectSquad: ['Выбрать отряд', 'Select squad'], scout: ['Разведка', 'Scouting'],
  free: ['Свободные игроки', 'Unassigned players'], emptySquads: ['Отряды ещё не назначены', 'No squads assigned yet'],
  search: ['Поиск игрока', 'Search players'], noResults: ['Игроки не найдены', 'No players found'],
};
export const tacticalMessage = (key, language) => (messages[key] || [key, key])[String(language).startsWith('en') ? 1 : 0];
