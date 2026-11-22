export const routeKey = order => `${order.territory_id}:${order.source_id ?? ''}:${order.route || 'land'}`;
export const assignPlayer = (orders, userId, order) => [
  ...orders.filter(row => row.user_id !== userId),
  ...(order ? [{ user_id: userId, source_id: null, territory_id: null, route: 'land', ...order }] : []),
];
export function planCounts(orders) {
  return { attacks: new Set(orders.filter(o => o.kind === 'attack').map(o => o.territory_id)).size,
    reserves: orders.filter(o => o.kind === 'reserve').length,
    ambush_players: orders.filter(o => o.kind === 'ambush').length };
}
export function planProblem(orders, data) {
  if (new Set(orders.map(o => o.user_id)).size !== orders.length) return 'duplicate';
  for (const order of orders) {
    const member = data.members.find(m => m.user_id === order.user_id);
    if (member?.scouting) return 'scouting';
    if (!member?.eligible) return 'ineligible';
    if (order.kind === 'reserve') {
      if (member.reserve_blocked) return 'reserveBlocked';
    } else if (order.kind === 'attack') {
      if (!data.attack_routes.some(route => routeKey(route) === routeKey(order))) return 'routeInvalid';
    } else if (order.kind === 'defend') {
      if (!data.defence_targets.includes(order.territory_id)) return 'routeInvalid';
    } else if (order.kind !== 'ambush') return 'routeInvalid';
  }
  const counts = planCounts(orders);
  if (counts.attacks > data.limits.attacks) return 'attackLimit';
  if (counts.reserves > data.limits.reserves) return 'reserveLimit';
  const ambushes = orders.filter(o => o.kind === 'ambush');
  if (ambushes.length > data.limits.ambush_players || new Set(ambushes.map(o => o.territory_id)).size > 1) return 'ambushLimit';
  const ordinary = new Set(orders.filter(o => ['attack', 'defend'].includes(o.kind)).map(o => o.territory_id));
  if (ambushes.some(o => !ordinary.has(o.territory_id))) return 'ambushSquad';
  return null;
}

const messages = {
  ordersTitle: ['Распределение отрядов', 'Squad assignments'],
  battles: ['Битвы цикла', 'Cycle battles'],
  loading: ['Загружаем план...', 'Loading plan...'],
  failed: ['Не удалось загрузить план. Изменения недоступны до обновления.', 'Could not load the plan. Refresh before making changes.'],
  clanless: ['Для просмотра плана нужно состоять в клане.', 'Join a clan to view its plan.'],
  retry: ['Обновить', 'Refresh'],
  save: ['Сохранить план', 'Save plan'],
  saving: ['Сохранение...', 'Saving...'],
  saved: ['План сохранён.', 'Plan saved.'],
  dirty: ['Есть несохранённые изменения', 'Unsaved changes'],
  readonly: ['Сейчас план доступен только для просмотра.', 'The plan is currently read-only.'],
  permission: ['План изменяют глава и воевода во время подготовки.', 'The head and voivodes can edit during preparation.'],
  deadline: ['Начало сражений', 'Battle start'],
  pending: ['Подготовка ещё не открыта.', 'Preparation has not opened yet.'],
  assignment: ['Назначение', 'Assignment'],
  destination: ['Территория и маршрут', 'Territory and route'],
  none: ['Без назначения', 'Unassigned'],
  attack: ['Атака', 'Attack'], defend: ['Оборона', 'Defend'], reserve: ['Запас', 'Reserve'], ambush: ['Засада', 'Ambush'],
  attacks: ['Атакуемые территории', 'Attacked territories'], reserves: ['Игроки в запасе', 'Reserve players'],
  ambush_players: ['Игроки в засаде', 'Ambush players'],
  choose: ['Выберите территорию', 'Select territory'],
  land: ['по суше', 'by land'], sea: ['по морю', 'by sea'], landing: ['Высадка', 'Landing'],
  blocked: ['Запас недоступен: не прошли два цикла отдыха.', 'Reserve unavailable: two cooldown cycles have not elapsed.'],
  noIdentity: ['Игрок недоступен для назначения.', 'Player unavailable for assignment.'],
  scouting: ['Разведчик до конца цикла: недоступен для сражений, засады, запаса и подкреплений.', 'Scout until the end of the cycle: unavailable for combat, ambush, reserve and reinforcements.'],
  noMembers: ['В клане нет игроков для распределения.', 'No players available for assignment.'],
  conflict: ['План изменился или подготовка завершилась. Ваш вариант сохранён на экране. Обновите план перед дальнейшими изменениями.', 'The plan changed or preparation ended. Your draft is still on screen. Refresh the plan before continuing.'],
  saveFailed: ['План не сохранён. Ваши изменения остались на экране.', 'Plan not saved. Your changes remain on screen.'],
  discard: ['Загрузить сохранённый план?', 'Load the saved plan?'],
  discardText: ['Несохранённые изменения будут заменены сохранённым планом клана.', 'Unsaved changes will be replaced with the saved clan plan.'],
  cancel: ['Отмена', 'Cancel'],
  warnings: ['При раскрытии не все назначения удалось сохранить.', 'Some assignments could not be retained at reveal.'],
  duplicate: ['У игрока может быть только одно назначение.', 'Each player can have only one assignment.'],
  ineligible: ['Уберите назначения недоступных игроков.', 'Remove assignments for unavailable players.'],
  reserveBlocked: ['Этот игрок пока не может быть в запасе.', 'This player is still on reserve cooldown.'],
  reserveLimit: ['Превышено число мест в запасе.', 'Reserve capacity exceeded.'],
  attackLimit: ['Превышен лимит атакуемых территорий.', 'Attack territory limit exceeded.'],
  routeInvalid: ['Выберите доступную территорию и маршрут для каждого отряда.', 'Select an available territory and route for each squad.'],
  ambushLimit: ['Можно отправить одну засаду из одного или двух игроков.', 'Only one ambush with one or two players is allowed.'],
  ambushSquad: ['Засаде нужен обычный отряд на той же территории.', 'An ambush needs an ordinary squad on the same territory.'],
};
export const planningMessage = (key, language) => (messages[key] || messages.failed)[String(language).startsWith('en') ? 1 : 0];
