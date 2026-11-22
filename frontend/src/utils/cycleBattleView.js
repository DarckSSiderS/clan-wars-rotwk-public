// Page-local copy keeps the independently owned cycle screen bilingual.
const messages = {
  cycle_entry_title: ['Битвы', 'Battles'],
  cycle_navigation: ['Разделы кампании', 'Campaign sections'],
  cycle_nav_battles: ['Битвы', 'Battles'],
  cycle_nav_orders: ['Отряды', 'Squads'],
  cycle_nav_reinforcements: ['Подкрепления', 'Reinforcements'],
  cycle_nav_diplomacy: ['Дипломатия', 'Diplomacy'],
  cycle_nav_economy: ['Казна', 'Treasury'],
  cycle_nav_preparation: ['Подготовка', 'Preparation'],
  cycle_campaign: ['Клановая кампания', 'Clan campaign'],
  cycle_number: ['Цикл', 'Cycle'],
  cycle_schedule: ['Сроки цикла', 'Cycle schedule'],
  cycle_map: ['Открыть карту', 'Open map'],
  cycle_clans_heading: ['Кланы в сражении', 'Clans in battle'],
  cycle_territories_heading: ['Сражения за территории', 'Territory battles'],
  cycle_view: ['Представление битв', 'Battle view'],
  cycle_view_clans: ['Кланы', 'Clans'],
  cycle_view_territories: ['Территории', 'Territories'],
  cycle_filter_all: ['Все', 'All'],
  cycle_filter_active: ['Без итогов', 'Unsettled'],
  cycle_filter_completed: ['Завершённые', 'Completed'],
  cycle_search: ['Клан или территория', 'Clan or territory'],
  cycle_clear_search: ['Очистить поиск', 'Clear search'],
  cycle_no_results: ['Ничего не найдено', 'Nothing found'],
  cycle_reset_filters: ['Сбросить фильтры', 'Reset filters'],
  cycle_territories_count: ['Территорий', 'Territories'],
  cycle_clans_count: ['Кланов', 'Clans'],
  cycle_finished_count: ['С итогами', 'Settled'],
  cycle_clan_battles: ['Сражения клана', 'Clan battles'],
  cycle_wins_count: ['Побед', 'Wins'],
  cycle_attack_count: ['В атаке', 'Attacking'],
  cycle_defense_count: ['В защите', 'Defending'],
  cycle_members_count: ['Участников', 'Members'],
  cycle_history: ['История', 'History'],
  cycle_admin_tools: ['Управление', 'Administration'],
  cycle_calculation: ['Расчёт очков', 'Score calculation'],
  cycle_match_info: ['Данные матча', 'Match details'],
  cycle_change_decision: ['Изменить зачёт', 'Change match decision'],
  cycle_match: ['Матч', 'Match'],
  cycle_match_counted: ['Засчитан', 'Counted'],
  cycle_match_rejected: ['Не засчитан', 'Not counted'],
  cycle_match_mixed: ['Частично засчитан', 'Partially counted'],
  cycle_winner: ['Победитель', 'Winner'],
  cycle_roster: ['Составы', 'Lineups'],
  cycle_empty_history: ['Событий пока нет', 'No events yet'],
  cycle_not_open: ['Цикл ещё не открыт', 'The cycle has not opened yet'],
  cycle_diplomacy: ['Дипломатия', 'Diplomacy'],
  cycle_orders: ['Распределение отрядов', 'Squad assignments'],
  cycle_reinforcements: ['Подкрепления и помощь', 'Reinforcements and help'],
  cycle_economy: ['Казна и развитие', 'Treasury and development'],
  cycle_preparation: ['Подготовка к кампании', 'Campaign preparation'],
  cycle_battles_title: ['Битвы цикла', 'Cycle battles'],
  common_clan: ['Клан', 'Clan'],
  cycle_player: ['Игрок', 'Player'],
  cycle_review: ['Пересмотр вклада', 'Review contribution'],
  cycle_adjust: ['Корректировка счёта', 'Adjust score'],
  cycle_counted: ['Учтён', 'Counted'],
  cycle_amount: ['Изменение очков', 'Score adjustment'],
  cycle_reason: ['Причина', 'Reason'],
  cycle_historical_elo: ['Elo на момент матча', 'Historical match Elo'],
  cycle_base_points: ['Базовые очки', 'Base points'],
  cycle_victory_bonus: ['Бонус победы', 'Victory bonus'],
  cycle_direct_multiplier: ['Прямой бой', 'Direct battle'],
  cycle_exhaustion_multiplier: ['Ослабление', 'Exhaustion'],
  common_saving: ['Сохранение...', 'Saving...'],
  common_save: ['Сохранить', 'Save'],
  common_saved: ['Сохранено', 'Saved'],
  common_retry: ['Повторить', 'Retry'],
  common_loading: ['Загрузка...', 'Loading...'],
  common_refresh: ['Обновить', 'Refresh'],
  cycle_no_winner: ['Не определён', 'Not assigned'],
  cycle_confirmed_winner: ['Подтверждённый победитель', 'Confirmed winner'],
  cycle_recalculated_winner: ['Победитель после пересчёта', 'Recalculated winner'],
  cycle_lineups: ['Стороны битвы', 'Battle sides'],
  cycle_no_members: ['Нет участников', 'No members'],
  cycle_matches: ['Матчи', 'Matches'],
  cycle_no_matches: ['Учтённых вкладов в матчи пока нет', 'No match contributions yet'],
  cycle_replay: ['Повтор', 'Replay'],
  cycle_contributions: ['вкладов игроков', 'player contributions'],
  cycle_excluded: ['Не учтён', 'Excluded'],
  cycle_review_reason: ['Причина пересмотра', 'Review reason'],
  cycle_adjustments: ['Корректировки счёта', 'Score adjustments'],
  cycle_no_adjustments: ['Корректировок нет', 'No adjustments'],
  cycle_late_title: ['Пропущенные матчи', 'Unrecorded matches'],
  cycle_late_scan: ['Проверить матчи', 'Check matches'],
  cycle_late_more: ['Проверить следующие матчи', 'Check next matches'],
  cycle_late_restart: ['Проверить заново', 'Check again'],
  cycle_late_empty: ['Пропущенных матчей не найдено', 'No unrecorded matches found'],
  cycle_late_partial: ['Проверена часть загруженных реплеев', 'Part of the imported replays has been checked'],
  cycle_late_warning: ['Эти матчи отсутствуют в итоговой сводке. Очки и владелец территории не изменены.', 'These matches are missing from the final summary. Scores and territory ownership have not changed.'],
  cycle_late_missing_elo: ['Не подтверждён Elo на момент матча', 'Historical match Elo is not verified'],
  cycle_late_open: ['Открыть реплей', 'Open replay'],
  cycle_late_review: ['Рассмотреть матч', 'Review match'],
  cycle_late_preview_refresh: ['Обновить расчёт', 'Refresh calculation'],
  cycle_late_preview: ['Предварительный расчёт', 'Calculation preview'],
  cycle_late_action: ['Решение по матчу', 'Match decision'],
  cycle_late_accept: ['Засчитать', 'Accept'],
  cycle_late_reject: ['Отклонить', 'Reject'],
  cycle_late_reason: ['Причина решения', 'Decision reason'],
  cycle_late_confirm: ['Подтверждаю решение без автоматической смены владельца', 'I confirm without automatically changing territory ownership'],
  cycle_late_submit: ['Сохранить решение', 'Save decision'],
  cycle_late_unavailable: ['Для зачёта не хватает подтверждённых данных либо нарушены условия участия. Можно отклонить матч или отдельно внести ручную поправку счёта с причиной.', 'Verified evidence is missing or participation rules are not met. Reject the match or use a separate manual score adjustment with a reason.'],
  cycle_map_income: ['Доход земли', 'Territory income'],
  cycle_map_without_relics: ['С улучшениями земли, без бонусов реликвий', 'Includes territory upgrades, excludes relic bonuses'],
  cycle_map_development: ['Текущее развитие', 'Current development'],
  cycle_map_land_influence: ['Влияние земли', 'Territory influence'],
  cycle_map_frozen_bonuses: ['Боевые бонусы действуют по состоянию на начало сражений.', 'Battle bonuses use the state at the start of combat.'],
  cycle_ownership_title: ['Исправление владения', 'Ownership correction'],
  cycle_ownership_open: ['Изменить владельца территории', 'Change territory owner'],
  cycle_ownership_current: ['Текущий владелец', 'Current owner'],
  cycle_ownership_new: ['Новый владелец', 'New owner'],
  cycle_ownership_neutral: ['Нейтральная земля', 'Neutral land'],
  cycle_ownership_warning: ['Передача действует с момента подтверждения. Прошлые доходы, результаты битв и уже отданные приказы сохраняются.', 'The transfer takes effect when confirmed. Past income, battle results and existing orders remain recorded.'],
  cycle_ownership_confirm: ['Подтверждаю передачу территории выбранному владельцу', 'I confirm the territory transfer to the selected owner'],
  cycle_ownership_submit: ['Подтвердить передачу', 'Confirm transfer'],
  cycle_ownership_refresh: ['Обновить данные владельца', 'Refresh ownership details'],
  cycle_ownership_history: ['Исправления владения', 'Ownership corrections'],
  cycle_territory: ['Территория', 'Territory'],
  cycle_completed: ['Завершена', 'Completed'],
  cycle_unsettled: ['Итоги ещё не подведены', 'Not settled'],
  cycle_defense: ['Защита', 'Defense'],
  cycle_attack: ['Атака', 'Attack'],
  cycle_details: ['Подробности битвы', 'Battle details'],
  cycle_phase: ['Этап', 'Phase'],
  cycle_starts_at: ['Начало цикла', 'Cycle starts'],
  cycle_preparation_at: ['Подготовка', 'Preparation'],
  cycle_battle_at: ['Начало битв', 'Battles start'],
  cycle_battle_ends_at: ['Окончание битв', 'Battles end'],
  cycle_replay_deadline: ['Срок загрузки повторов', 'Replay deadline'],
  cycle_replay_loading_started_at: ['Загрузка повторов', 'Replay upload', 'Replay-Import'],
  cycle_settled_at: ['Подведение итогов', 'Settlement'],
  cycle_rest_started_at: ['Начало перерыва', 'Break starts', 'Pause beginnt'],
  cycle_next_cycle_starts_at: ['Начало цикла {number}', 'Cycle {number} starts', 'Zyklus {number} beginnt'],
  cycle_next_cycle_pending: ['После итогов и перерыва', 'After settlement and break', 'Nach Auswertung und Pause'],
  cycle_settlement_pending: ['Время ещё не известно', 'Time not yet known', 'Zeit noch nicht bekannt'],
  cycle_current_stage: ['Текущий этап', 'Current phase', 'Aktuelle Phase'],
  cycle_empty: ['В этом цикле пока нет битв', 'No battles in this cycle yet'],
  cycle_all_clans: ['Все кланы', 'All clans'],
  cycle_battles_count: ['битв', 'battles'],
  cycle_total_score: ['Всего очков', 'Total score'],
  cycle_request_failed: ['Не удалось выполнить запрос', 'The request could not be completed'],
  cycle_error_details: ['Подробности ошибки', 'Error details'],
  cycle_unknown_phase: ['Статус пока недоступен', 'Status is not available yet'],
  cycle_unknown_reason: ['Причина не распознана', 'Unrecognized reason'],
};

const phases = {
  scheduled: ['Запланирован', 'Scheduled'],
  registration: ['Регистрация', 'Registration'],
  preparation: ['Подготовка', 'Preparation'],
  battle: ['Битвы', 'Battles'],
  replay_loading: ['Загрузка повторов', 'Replay upload'],
  settlement: ['Подведение итогов', 'Settlement'],
  rest: ['Отдых', 'Rest'],
  complete: ['Цикл завершён', 'Cycle complete'],
  season_ended: ['Сезон завершён', 'Season ended'],
};

const reasons = {
  not_ranked: ['Матч не рейтинговый', 'Match is not ranked'],
  unsupported_patch: ['Матч сыгран не на Ennorath', 'Match was not played on Ennorath'],
  missing_match_times: ['Не подтверждены начало и окончание матча', 'Match start and finish are not verified'],
  invalid_match_times: ['Некорректное время начала или окончания матча', 'Match start or finish time is invalid'],
  too_short: ['Матч длился меньше одной минуты', 'Match lasted less than one minute'],
  outside_battle_window: ['Матч начался или закончился вне времени битвы', 'Match started or finished outside the battle window'],
  reinforcement_blocked: ['Подкрепление остановлено в перехвате', 'Reinforcement was blocked by an interception'],
  reinforcement_not_arrived: ['На момент начала матча подкрепление ещё не прибыло', 'Reinforcement had not arrived when the match started'],
  interception_pending: ['Ожидается исход перехвата подкрепления', 'Waiting for the reinforcement interception outcome'],
  ambush_opponent: ['Соперник участвует в другой засаде этого перехвата', 'The opponent belongs to another ambush in this interception'],
  membership_changed: ['Выход или позднее вступление в клан не позволяют участвовать в этом цикле', 'Leaving the clan or joining after battles started prevents participation in this cycle'],
  scouting: ['Игрок отправлен в разведку и не участвует в сражениях до конца цикла', 'The player is scouting and cannot take part in battles until the cycle ends'],
  not_assigned: ['Игрок не назначен в эту битву', 'Player is not assigned to this battle'],
  clan_opponent: ['В команде соперника есть соклановец', 'A clan member is on the opposing team'],
  allied_opponent: ['В команде соперника есть союзник', 'An ally is on the opposing team'],
  draw: ['Ничья', 'Draw'],
  unknown_result: ['Результат матча неизвестен', 'Match result is unknown'],
  missing_historical_elo: ['Нет рейтинга Elo на момент матча', 'Historical match Elo is unavailable'],
  counted: ['Вклад учтён', 'Contribution counted'],
};

const languageIndex = language => /^en(?:g|[-_].*)?$/i.test(language || '') ? 1 : 0;
export const cycleMessage = (key, language) => messages[key]?.[languageIndex(language)] || '-';
export const cyclePhaseLabel = (phase, language) => phases[phase]?.[languageIndex(language)] || cycleMessage('cycle_unknown_phase', language);
export function cycleReasonLabel(reason, language) {
  if (!reason) return '-';
  if (reasons[reason]) return reasons[reason][languageIndex(language)];
  return /^[a-z][a-z0-9]*(?:_[a-z0-9]+)+$/i.test(reason)
    ? cycleMessage('cycle_unknown_reason', language) : reason;
}

export function reviewCounted(contribution, draft) {
  const current = Boolean(contribution?.counted);
  return draft?.original === current ? draft.value : current;
}

export function selectTerritoryBattle(battles, territory, user) {
  if (!/^[0-9]+$/.test(String(territory ?? '')) || Number(territory) <= 0) return null;
  const battle = battles.find(row => String(row.territory_id) === String(Number(territory)));
  if (!battle) return null;
  const clanId = user?.current_clan_id ?? user?.current_clan?.id ?? user?.clan_id ?? user?.clan?.id;
  const sides = battle.sides || [];
  const side = sides.find(row => clanId != null && String(row.clan_id) === String(clanId)) || sides[0];
  return { battle, clan_id: side?.clan_id ?? null };
}

export function formatScore(value) {
  if (value == null || value === '') return '-';
  let text = String(value);
  const scientific = text.match(/^(-?)(\d+)(?:\.(\d+))?[eE]([+-]?\d+)$/);
  if (scientific && Math.abs(Number(scientific[4])) <= 100) {
    const [, sign, whole, fraction = '', exponent] = scientific;
    const digits = whole + fraction, position = whole.length + Number(exponent);
    text = sign + (position <= 0 ? `0.${'0'.repeat(-position)}${digits}`
      : position >= digits.length ? digits + '0'.repeat(position - digits.length)
        : `${digits.slice(0, position)}.${digits.slice(position)}`);
  }
  const formatted = text.includes('.') ? text.replace(/0+$/, '').replace(/\.$/, '') : text;
  return /^-?0+$/.test(formatted) ? '0' : formatted;
}

// API decimals have at most twelve places; retain exact totals without float rounding.
function scoreUnits(value) {
  const text = formatScore(value ?? 0);
  const [whole, fraction = ''] = text.replace(/^-/, '').split('.');
  return BigInt(`${whole}${fraction.padEnd(12, '0')}`) * (text.startsWith('-') ? -1n : 1n);
}

export function sumScores(values) {
  const units = values.reduce((total, value) => total + scoreUnits(value), 0n);
  const digits = (units < 0n ? -units : units).toString().padStart(13, '0');
  return formatScore(`${units < 0n ? '-' : ''}${digits.slice(0, -12)}.${digits.slice(-12)}`);
}

export function groupClanBattles(battles = []) {
  const clans = new Map();
  battles.forEach(battle => (battle.sides || []).forEach(side => {
    let clan = clans.get(side.clan_id);
    if (!clan) {
      clan = { clan_id: side.clan_id, battles: [], units: 0n };
      clans.set(side.clan_id, clan);
    }
    clan.clan_name = side.clan_name || clan.clan_name;
    clan.avatar_url = side.avatar_url || clan.avatar_url;
    clan.battles.push(battle);
    clan.units += scoreUnits(side.score);
  }));
  return [...clans.values()].map(({ units, ...clan }) => {
    const digits = (units < 0n ? -units : units).toString().padStart(13, '0');
    return { ...clan, score: formatScore(`${units < 0n ? '-' : ''}${digits.slice(0, -12)}.${digits.slice(-12)}`) };
  });
}

export function groupContributions(rows = []) {
  const groups = new Map();
  rows.forEach(row => {
    if (!groups.has(row.replay_id)) groups.set(row.replay_id, { replay_id: row.replay_id, contributions: [] });
    groups.get(row.replay_id).contributions.push(row);
  });
  return [...groups.values()];
}

export function createAdjustmentCommand(makeId = () => globalThis.crypto.randomUUID()) {
  let key;
  let id;
  return {
    get(payload) {
      const next = JSON.stringify(Object.keys(payload).sort().map(key => [key, payload[key]]));
      if (next !== key) { key = next; id = makeId(); }
      return id;
    },
    reset() { key = undefined; id = undefined; },
  };
}
