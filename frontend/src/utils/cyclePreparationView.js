export function scoutOrderAvailable(data, payload) {
  const scout = data?.scout;
  return Boolean(payload && scout?.can_request && !scout.request && scout.wallet_revision != null
    && payload.expected_revision === scout.wallet_revision
    && data.territories.some(land => land.id === payload.territory_id)
    && scout.players?.some(player => player.user_id === payload.scout_user_id));
}

const messages = {
  screen: ['Подготовка к кампании', 'Campaign preparation'], scout: ['Разведка', 'Scouting'], startup: ['Стартовые земли', 'Starting lands'],
  target: ['Цель разведки', 'Scout target'], choose: ['Выберите территорию', 'Select territory'], order: ['Заказать разведку', 'Order scouting'],
  scoutPlayer: ['Разведчик', 'Scout'], chooseScout: ['Выберите разведчика', 'Select scout'],
  scoutUnassigned: ['Разведка заказана без назначения игрока.', 'Scouting was ordered without assigning a player.'],
  noScoutPlayers: ['Нет свободных подтверждённых игроков клана для разведки.', 'No free verified clan members are available for scouting.'],
  noFreeScout: ['Нет свободного игрока: снимите с подтверждённого участника клана назначение в отрядах, затем обновите сведения.', 'No free player: remove a verified clan member\'s squad assignment, then refresh.'],
  scoutNoPermission: ['Разведку заказывают глава или воевода клана.', 'Only the clan head or voivode can order scouting.'],
  scoutOutsidePreparation: ['Разведку можно заказать только во время подготовки.', 'Scouting can only be ordered during preparation.'],
  scoutCutoffPassed: ['Приём заказов разведки завершён: до боя осталось менее 6 часов.', 'Scouting orders are closed: less than 6 hours remain before battle.'],
  scoutAlreadyRequested: ['Разведка уже заказана на этот цикл.', 'Scouting has already been ordered for this cycle.'],
  scoutEconomyMissing: ['Разведка недоступна: казна нового сезона ещё не открыта.', 'Scouting is unavailable: the seasonal treasury has not opened yet.'],
  scoutLock: ['Разведчик закреплён до конца цикла: не может сражаться, участвовать в засаде, быть в запасе или идти в подкрепление. Заменить разведчика нельзя.', 'The scout is locked until the end of the cycle: cannot fight, ambush, be in reserve or reinforce. The scout cannot be replaced.'],
  scoutStale: ['Данные изменились. Выберите разведчика заново и подтвердите заказ.', 'Data changed. Select the scout again and confirm the order.'],
  paid: ['Стоимость — 200 золота. После оплаты изменить цель нельзя.', 'Cost: 200 gold. You cannot change the paid target.'],
  reportAt: ['Отчёт будет доступен', 'Report available at'], waiting: ['Разведчики ещё не вернулись.', 'Scouts have not returned yet.'],
  report: ['Обнаруженные отряды', 'Detected squads'], noSquads: ['Обычных отрядов не обнаружено.', 'No ordinary squads detected.'],
  squad: ['Численность отряда', 'Squad size'], landsRule: ['Выберите три связанные земли. Порты и крепости недоступны. Существующие владения учитываются вместо нового подарка.', 'Choose three connected territories. Ports and fortresses are excluded. Existing holdings count instead of an additional gift.'],
  preview: ['Проверить выбор', 'Review selection'], release: ['Земли, которые станут нейтральными', 'Territories to be released'],
  selected: ['Выбранные земли', 'Selected territories'], claim: ['Закрепить земли', 'Claim territories'],
  closed: ['Выбор сейчас недоступен. Автоматической выдачи земель нет.', 'Selection is currently unavailable. No territories are granted automatically.'],
  pendingInit: ['Стартовое распределение ещё не открыто.', 'Starting distribution has not opened yet.'], search: ['Поиск территории', 'Search territories'],
  deadline: ['Выбор до', 'Selection deadline'], loading: ['Загрузка...', 'Loading...'], refresh: ['Обновить', 'Refresh'],
  failed: ['Действие недоступно или данные изменились. Обновите сведения. Для старта нужны три связанные допустимые земли.', 'Action unavailable or data changed. Refresh. Starting selection requires three connected eligible territories.'],
  clanless: ['Вступите в клан для подготовки кампании.', 'Join a clan for campaign preparation.'],
  saved: ['Действие выполнено.', 'Action completed.'], confirm: ['Подтвердить', 'Confirm'], cancel: ['Отмена', 'Cancel'],
};
export const preparationMessage = (key, language) => (messages[key] || messages.failed)[String(language).startsWith('en') ? 1 : 0];
