// Local bilingual copy: this independently owned page does not change global keys.
const messages = {
  diplomacy_title: ['Дипломатия', 'Diplomacy'],
  cycle: ['Цикл', 'Cycle'],
  phase: ['Этап', 'Phase'],
  refresh: ['Обновить', 'Refresh'],
  loading: ['Загрузка отношений...', 'Loading relations...'],
  failed: ['Не удалось загрузить отношения.', 'Could not load relations.'],
  privateFailed: ['Управление недоступно: не удалось загрузить данные клана.', 'Management unavailable: clan data could not be loaded.'],
  actionFailed: ['Действие не выполнено. Проверьте обновлённые отношения и повторите.', 'Action failed. Check the refreshed relations and try again.'],
  conflict: ['Данные изменились или действие уже недоступно. Отношения обновлены; проверьте их перед повтором.', 'Data changed or this action is no longer available. Relations were refreshed; review before retrying.'],
  saved: ['Действие выполнено.', 'Action completed.'],
  search: ['Поиск по клану', 'Search clans'],
  filter: ['Отношения', 'Relations'],
  all: ['Все отношения', 'All relations'],
  allies: ['Союзы', 'Alliances'],
  enemies: ['Вражда', 'Hostilities'],
  neutrals: ['Нейтральные отношения', 'Neutral relations'],
  relations_empty: ['Отношений по этому запросу нет.', 'No relations match this search.'],
  clear: ['Сбросить фильтры', 'Clear filters'],
  clan: ['Клан', 'Clan'],
  deleted: ['Недоступный клан', 'Unavailable clan'],
  management: ['Управление дипломатией', 'Diplomacy management'],
  target: ['Другой клан', 'Other clan'],
  choose: ['Выберите клан', 'Select a clan'],
  blocked: ['Изменения доступны только в подготовку и перерыв.', 'Changes are available only during preparation and rest.'],
  offerAlliance: ['Предложить союз', 'Offer alliance'],
  offerPeace: ['Предложить мир', 'Offer peace'],
  war: ['Объявить войну', 'Declare war'],
  break: ['Расторгнуть союз', 'Break alliance'],
  duration: ['Количество циклов', 'Number of cycles'],
  indefinite: ['До заключения мира', 'Until mutual peace'],
  finite: ['На выбранное число циклов', 'For a chosen number of cycles'],
  durationMode: ['Срок войны', 'War duration'],
  durationError: ['Введите целое число от 1.', 'Enter a whole number of at least 1.'],
  remaining: ['Осталось циклов', 'Cycles remaining'],
  ends: ['До расчёта цикла', 'Through settlement of cycle'],
  since: ['Дата заключения', 'Allied since'],
  declared: ['Дата объявления', 'Declared on'],
  proposals: ['Предложения вашего клана', 'Your clan proposals'],
  noProposals: ['Предложений нет.', 'No proposals.'],
  accept: ['Принять', 'Accept'],
  revoke: ['Отозвать', 'Revoke'],
  incoming: ['Входящее', 'Incoming'],
  outgoing: ['Исходящее', 'Outgoing'],
  expires: ['Действует до расчёта цикла', 'Expires after settlement of cycle'],
  created: ['Создано', 'Created'],
  confirmWar: ['Объявить войну этому клану?', 'Declare war on this clan?'],
  confirmBreak: ['Расторгнуть союз с этим кланом?', 'Break the alliance with this clan?'],
  cancel: ['Отмена', 'Cancel'],
  confirm: ['Подтвердить', 'Confirm'],
  unavailable: ['Недоступно', 'Unavailable'],
};
const labels = {
  allied: ['Союз', 'Allied'], hostile: ['Вражда', 'Hostile'], neutral: ['Нейтралитет', 'Neutral'],
  pending: ['Ожидает ответа', 'Pending'], accepted: ['Принято', 'Accepted'],
  revoked: ['Отозвано', 'Revoked'], expired: ['Срок истёк', 'Expired'],
  alliance: ['Союз', 'Alliance'], peace: ['Мир', 'Peace'],
  attack: ['Война после раскрытого нападения', 'War from a revealed attack'],
  declaration: ['Объявление войны', 'War declaration'],
};
const english = language => String(language || '').toLowerCase().startsWith('en');
export const diplomacyMessage = (key, language) => (messages[key] || messages.unavailable)[english(language) ? 1 : 0];
export const diplomacyLabel = (key, language) => (labels[key] || messages.unavailable)[english(language) ? 1 : 0];
export const isDiplomacyHead = (user, clan) => Boolean(user?.id && clan?.id && !clan.is_deleted && user.id === clan.leader_id);
export const diplomacyEditable = phase => phase === 'preparation' || phase === 'rest';

export function parseWarDuration(value, indefinite) {
  if (indefinite) return null;
  const digits = String(value ?? '').trim();
  if (!/^[0-9]+$/.test(digits) || !/[1-9]/.test(digits)) throw new Error('Invalid duration');
  return digits.replace(/^0+/, '');
}

export function filterRelations(relations, search = '', status = 'all') {
  const query = search.trim().toLocaleLowerCase();
  return (relations || []).filter(row => (status === 'all' || row.status === status) &&
    (!query || [row.clan_low?.name, row.clan_high?.name].some(name => name?.toLocaleLowerCase().includes(query))));
}

export const relationForClan = (relations, ownId, otherId) => (relations || []).find(row =>
  (row.clan_low_id === ownId && row.clan_high_id === otherId) ||
  (row.clan_high_id === ownId && row.clan_low_id === otherId)) || null;

export const pairRevision = (own, otherId) => own?.pairs?.find(row => row.other_clan_id === otherId)?.revision ?? 0;

export function buildDiplomacyAction({ action, otherClanId, own, duration, proposalId }) {
  if (!['declare_war', 'offer_alliance', 'offer_peace', 'break_alliance', 'accept', 'revoke'].includes(action) ||
      !Number.isSafeInteger(otherClanId) || otherClanId < 1) throw new Error('Invalid action');
  const payload = { action, other_clan_id: otherClanId, expected_revision: pairRevision(own, otherClanId) };
  if (action === 'declare_war') payload.duration = duration === null ? null : parseWarDuration(duration, false);
  if (action === 'accept' || action === 'revoke') {
    if (!Number.isSafeInteger(proposalId) || proposalId < 1) throw new Error('Invalid proposal');
    payload.proposal_id = proposalId;
  }
  return payload;
}
