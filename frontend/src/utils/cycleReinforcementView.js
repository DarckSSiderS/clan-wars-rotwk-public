export const dispatchTargetKey = target => `${target.recipient_clan_id}:${target.territory_id}:${target.request_id || ''}`;
export function reinforcementCommand(previous, action, target, players, newId = () => crypto.randomUUID()) {
  const signature = JSON.stringify([action, dispatchTargetKey(target), [...players].sort((a, b) => a - b),
    action === 'dispatch' ? target.origin_territory_id ?? null : null]);
  return previous?.signature === signature ? previous : { signature, id: newId(), action };
}
export function dispatchState(dispatch, now) {
  if (dispatch.outcome === 'blocked' || dispatch.outcome === 'pending') return dispatch.outcome;
  if (now < Date.parse(dispatch.arrives_at)) return 'travelling';
  return dispatch.outcome === 'exhausted' ? 'arrivedExhausted' : 'arrived';
}
export function dispatchCountdown(dispatch, now) {
  const seconds = Math.max(0, Math.ceil((Date.parse(dispatch.arrives_at) - now) / 1000));
  return [Math.floor(seconds / 3600), Math.floor(seconds / 60) % 60, seconds % 60]
    .map(value => String(value).padStart(2, '0')).join(':');
}
export function dispatchRouteDrawing(route, boxes) {
  if (!route?.nodes?.length) return null;
  const mapped = route.status === 'mapped';
  const ids = mapped ? route.territory_ids : [route.target_territory_id];
  if (!ids?.length || (mapped && (ids[0] !== route.origin_territory_id || ids.at(-1) !== route.target_territory_id))) return null;
  const bounds = ids.map(id => boxes.get(id));
  if (bounds.some(box => !box || ![box.x, box.y, box.width, box.height].every(Number.isFinite) || box.width <= 0 || box.height <= 0)) return null;
  const centers = bounds.map(box => [box.x + box.width / 2, box.y + box.height / 2]);
  const left = Math.min(...bounds.map(b => b.x)), top = Math.min(...bounds.map(b => b.y));
  const right = Math.max(...bounds.map(b => b.x + b.width)), bottom = Math.max(...bounds.map(b => b.y + b.height));
  const padding = Math.max(right - left, bottom - top) * 0.08;
  return { points: mapped ? centers : [], target: centers.at(-1), origin: mapped ? centers[0] : null,
    viewBox: [left - padding, top - padding, right - left + padding * 2, bottom - top + padding * 2] };
}
const messages = {
  screen: ['Подкрепления и помощь', 'Reinforcements and help'],
  battles: ['Битвы цикла', 'Cycle battles'],
  refresh: ['Обновить', 'Refresh'],
  loading: ['Загрузка подкреплений...', 'Loading reinforcements...'],
  loadFailed: ['Не удалось обновить подкрепления. Отправка недоступна до обновления.', 'Could not refresh reinforcements. Sending is disabled until refresh succeeds.'],
  clanless: ['Для просмотра подкреплений нужно состоять в клане.', 'Join a clan to view reinforcements.'],
  notReady: ['Подкрепления станут доступны после раскрытия отрядов.', 'Reinforcements become available after squad reveal.'],
  readonly: ['Отправлять запас и запрашивать помощь могут глава и воевода в первые 24 часа сражений.', 'The head and voivodes can dispatch reserves and request help during the first 24 battle hours.'],
  deadline: ['Отправка доступна до', 'Dispatch deadline'],
  reserve: ['Запас клана', 'Clan reserve'],
  noReserve: ['На этот цикл запас не назначен.', 'No reserve was selected for this cycle.'],
  already_sent: ['Уже отправлен', 'Already dispatched'],
  ineligible: ['Недоступен: изменилось членство в клане', 'Unavailable: clan membership changed'],
  identity_changed: ['Недоступен: проверьте привязку к Арене', 'Unavailable: check Arena identity'],
  target: ['Куда отправить', 'Destination'],
  origin: ['Земля отправления', 'Origin territory'],
  chooseOrigin: ['Выберите свою землю', 'Select your territory'],
  route: ['Маршрут подкрепления', 'Reinforcement route'],
  routeMapped: ['Маршрут', 'Route'],
  routeUnreachable: ['На карте нет связного пути до цели. Путь не отображается.', 'No connected map path to the destination. No route is drawn.'],
  routeLandless: ['У клана нет земель: указана только цель.', 'Your clan has no territories: destination only.'],
  routeLegacy: ['Маршрут этой отправки не сохранён.', 'No route was saved for this dispatch.'],
  routeGeometry: ['Геометрия маршрута недоступна.', 'Route geometry is unavailable.'],
  remaining: ['До прибытия', 'Time to arrival'],
  choose: ['Выберите территорию', 'Select territory'],
  own: ['Свои сражения', 'Own battles'],
  allied: ['Запросы союзников', 'Allied requests'],
  noAllied: ['Открытых запросов союзников нет.', 'No open allied requests.'],
  send: ['Отправить подкрепление', 'Dispatch reinforcement'],
  confirm: ['Отправить', 'Dispatch'],
  confirmHeading: ['Отправить этот отряд?', 'Dispatch this squad?'],
  confirmText: ['Путь займёт 24 часа. Отменить отправку или изменить цель нельзя. Матчи начнут учитываться только после прибытия.', 'Travel takes 24 hours. You cannot cancel or change the destination. Matches count only after arrival.'],
  cancel: ['Отмена', 'Cancel'],
  selected: ['Выбранные игроки', 'Selected players'],
  assistance: ['Помощь вашему клану', 'Help for your clan'],
  request: ['Запросить помощь союзников', 'Request allied help'],
  waiting: ['Помощь запрошена', 'Help requested'],
  incoming: ['Помощь уже в пути', 'Help is already on the way'],
  noBattles: ['У клана нет сражений в этом цикле.', 'Your clan has no battles in this cycle.'],
  requested: ['Запрос отправлен.', 'Help requested.'],
  sent: ['Подкрепление отправлено.', 'Reinforcement dispatched.'],
  failed: ['Действие не подтверждено. Обновите данные или повторите попытку. Повтор не создаст второй отряд.', 'Action not confirmed. Refresh or retry. Retrying will not create a second squad.'],
  conflict: ['Данные изменились или отправка уже недоступна. Проверьте обновлённые сведения и подтвердите состав заново.', 'Data changed or dispatch is no longer available. Review refreshed information and confirm again.'],
  movements: ['Отряды в пути', 'Squad movements'],
  noMovements: ['Отправленных отрядов пока нет.', 'No dispatched squads yet.'],
  sentAt: ['Отправлен', 'Dispatched'],
  arrival: ['Прибытие', 'Arrival'],
  travelling: ['В пути', 'Travelling'],
  pending: ['Перехват: ожидается исход', 'Interception: outcome pending'],
  blocked: ['Подкрепление остановлено', 'Reinforcement blocked'],
  arrived: ['Прибыл', 'Arrived'],
  arrivedExhausted: ['Прибыл ослабленным: 50% очков', 'Arrived exhausted: 50% points'],
  interception: ['Начало перехвата', 'Interception starts'],
  interceptionEnd: ['Окончание перехвата', 'Interception ends'],
  battle: ['Открыть сражение', 'Open battle'],
  unavailableClan: ['Недоступный клан', 'Unavailable clan'],
};
export const reinforcementMessage = (key, language) => (messages[key] || messages.failed)[String(language).startsWith('en') ? 1 : 0];
