const messages = {
  orders: ['Распределить отряд', 'Assign squad'], scout: ['Разведать территорию', 'Scout territory'],
  reinforcements: ['Отправить подкрепление', 'Send reinforcements'],
  action: ['Приказ', 'Order'], players: ['Игроки отряда', 'Squad players'],
  current: ['Сейчас', 'Currently'], review: ['Проверить приказ', 'Review order'],
  confirmOrder: ['Подтвердить приказ', 'Confirm order'], confirm: ['Подтвердить', 'Confirm'],
  close: ['Закрыть', 'Close'], cancel: ['Отмена', 'Cancel'], loading: ['Загрузка...', 'Loading...'],
  reassignment: ['Назначения выбранных игроков будут заменены. Остальные приказы клана сохранятся.', 'Selected players will be reassigned. Other clan orders remain unchanged.'],
  unavailable: ['На этой территории сейчас нет доступного назначения. Проверьте этап цикла и маршрут.', 'No assignment is currently available here. Check the cycle phase and route.'],
  attackDestination: ['Цель атаки', 'Attack destination'], attackSource: ['Земля отправления и маршрут', 'Origin territory and route'],
  chooseAttack: ['Выберите доступную цель', 'Select an available destination'],
  noAttackDestinations: ['Доступных целей атаки сейчас нет.', 'No attack destinations are currently available.'],
  attackUnavailable: ['Атака этой территории недоступна.', 'This territory cannot currently be attacked.'],
  owned: ['Нельзя атаковать свою территорию. Здесь можно назначить оборону.', 'You cannot attack your own territory. You can assign defence here.'],
  ally: ['Нельзя атаковать территорию союзника.', 'You cannot attack an allied territory.'],
  no_eligible_players: ['В клане нет доступных игроков для атаки. Проверьте членство и привязку к Арене.', 'There are no eligible players for an attack. Check clan membership and Arena identities.'],
  fortress_requirements: ['Для атаки крепости нужны как минимум 5 земель и 350 влияния; клан без земель не может атаковать порты и крепости.', 'Attacking a fortress requires at least 5 lands and 350 influence; landless clans cannot attack ports or fortresses.'],
  landless_port: ['Клан без земель не может атаковать порт. Сначала захватите обычную территорию.', 'A landless clan cannot attack a port. Capture an ordinary territory first.'],
  no_adjacent_land_or_port: ['Нет соседней своей земли или подходящего морского маршрута из своего порта к этой территории.', 'There is no adjacent owned land or valid sea route from an owned port to this territory.'],
  snapshot_missing: ['Снимок подготовки ещё не готов. Доступные маршруты появятся после его создания.', 'The preparation snapshot is not ready. Available routes will appear once it is captured.'],
  scoutingUnavailable: ['Разведку заказывают глава или воевода во время подготовки, не позднее чем за 6 часов до боя. Нужна казна нового сезона.', 'The head or voivode can order scouting during preparation, at least 6 hours before battle. A seasonal treasury is required.'],
};
export const mapCommandMessage = (key, language) => messages[key]?.[String(language).startsWith('en') ? 1 : 0] || key;

export function mapAttackUnavailableReason(data, territoryId) {
  if (!data.snapshot_ready) return 'snapshot_missing';
  const reason = data.attack_unavailable?.find(item => item.territory_id === territoryId)?.reason;
  return ['owned', 'ally', 'no_eligible_players', 'fortress_requirements', 'landless_port', 'no_adjacent_land_or_port', 'snapshot_missing'].includes(reason)
    ? reason : 'attackUnavailable';
}

export function mapReinforcementTarget(data, territoryId, now) {
  if (!data?.ready || !data.can_command || data.phase !== 'battle' || !Number.isFinite(now)
    || !(now < Date.parse(data.command_deadline)) || !data.players?.some(player => player.available)) return null;
  const own = data.own_targets?.find(target => target.territory_id === territoryId);
  if (own) return { ...own, recipient_clan_id: data.clan_id, request_id: null };
  return data.allied_targets?.find(target => target.territory_id === territoryId && target.request_id && target.recipient_clan_id) || null;
}
