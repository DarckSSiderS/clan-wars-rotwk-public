const messages = {
  screen: ['Перехват подкрепления', 'Reinforcement interception'],
  positive: ['За победы', 'From wins'], negative: ['За поражения', 'From losses'], total: ['Итог', 'Net'],
  help: ['Подкрепление', 'Reinforcement'], ambush: ['Засада', 'Ambush'],
  blocked: ['Подкрепление остановлено и не участвует в битве за территорию.', 'Reinforcement was stopped and cannot contribute to the territory battle.'],
  exhausted: ['Подкрепление продолжает путь с половиной вклада.', 'Reinforcement continues with half its territorial contribution.'],
  pending: ['Исход перехвата ещё не определён.', 'The interception outcome is not decided yet.'],
  battle: ['Идёт перехват', 'Interception in progress'], replay_loading: ['Догрузка последних матчей', 'Loading final matches'],
  settlement: ['Ожидается проверка и расчёт', 'Waiting for verification and settlement'], completed: ['Перехват рассчитан', 'Interception settled'],
  start: ['Начало перехвата', 'Interception starts'], end: ['Окончание перехвата', 'Interception ends'],
  deadline: ['Приём последних реплеев', 'Final replay deadline'], arrival: ['Плановое прибытие', 'Scheduled arrival'],
  territory: ['Битва за территорию', 'Territory battle'], open: ['Открыть перехват', 'Open interception'],
};
export const interceptionMessage = (key, language) => messages[key]?.[String(language).startsWith('en') ? 1 : 0] || '-';
export const interceptionPath = (cycleId, dispatchId) => `/campaign/cycles/${encodeURIComponent(cycleId)}/interception?dispatch=${encodeURIComponent(dispatchId)}`;

const reviewMessages = {
  review: 'Пересмотр вклада', adjust: 'Ручная поправка', reason: 'Причина',
  amount: 'Изменение очков', side: 'Сторона перехвата', save: 'Сохранить правку',
  exclude: 'Исключить из зачёта', restore: 'Вернуть в зачёт', cancel: 'Отмена',
  confirm_edit: 'Подтверждаю исправление истории счёта без изменения исхода подкрепления',
  history: 'Исправленный счёт', applied: 'Применённый исход', original: 'Первоначальный исход',
  missing_elo: 'Исторический Elo не подтверждён. Ручная поправка учитывается отдельно.',
  manual: 'Ручные поправки', reviewed: 'Пересмотрено администратором',
  preview: 'Предпросмотр изменения исхода', confirm: 'Применить исход подкрепления',
  outcome: 'Изменение судьбы подкрепления', proposed: 'Новый исход',
  confirm_outcome: 'Подтверждаю изменение судьбы подкрепления до его прибытия',
  arrival_locked: 'После прибытия разрешены только правки истории счёта. Матчи, захваты и доход не откатываются.',
  pending_window: 'Изменение исхода доступно после приёма последних реплеев и до прибытия.',
  stale: 'Данные изменились. Обновите страницу и повторите предпросмотр.',
  error: 'Не удалось выполнить действие. Проверьте данные и повторите запрос.',
  saving: 'Сохранение...', saved: 'Правка сохранена', loading: 'Загрузка...',
  audit: 'Журнал пересмотра', actor: 'Администратор', revision: 'Версия',
  review_action: 'Пересмотр вклада', adjust_action: 'Поправка очков',
  preview_outcome_action: 'Предпросмотр исхода', confirm_outcome_action: 'Подтверждение исхода',
  no_audit: 'Пересмотров ещё не было.',
  counted: 'Учитывать вклад', command_storage_error: 'Повреждено локальное хранилище команд пересмотра',
};

export const interceptionReviewMessage = key => reviewMessages[key] || '-';

export function canRestoreInterceptionContribution(row) {
  return row?.reason === 'counted' && row.calculation?.historical_elo != null;
}

export function canChangeInterceptionOutcome(data, elapsedMs = 0) {
  const now = Date.parse(data?.server_time) + Math.max(0, elapsedMs);
  return Number.isInteger(data?.revision) && Number.isFinite(now)
    && now >= Date.parse(data.replay_deadline) && now < Date.parse(data.arrives_at);
}

export function canConfirmInterceptionOutcome(data, preview, elapsedMs = 0) {
  return preview?.revision === data?.revision && canChangeInterceptionOutcome(data, elapsedMs);
}

export function createInterceptionCommandStore(storage, scope, makeId = () => globalThis.crypto.randomUUID()) {
  const key = `cw:interception-review:${scope}`;
  const pendingKey = `${key}:pending`;
  const signature = (action, payload) => JSON.stringify([action, Object.keys(payload)
    .filter(name => name !== 'expected_revision').sort().map(name => [name, payload[name]])]);
  const pending = () => {
    const values = JSON.parse(storage.getItem(pendingKey) || '{}');
    if (!values || Array.isArray(values) || typeof values !== 'object'
        || Object.values(values).some(value => !value || typeof value.command_id !== 'string'
          || !Number.isInteger(value.expected_revision))) {
      throw new Error(interceptionReviewMessage('command_storage_error'));
    }
    return values;
  };
  return {
    get(action, payload) {
      const values = JSON.parse(storage.getItem(key) || '{}');
      if (!values || Array.isArray(values) || typeof values !== 'object'
          || Object.values(values).some(value => typeof value !== 'string')) {
        throw new Error(interceptionReviewMessage('command_storage_error'));
      }
      const signature = JSON.stringify([action, Object.keys(payload).sort().map(name => [name, payload[name]])]);
      if (!values[signature]) values[signature] = makeId();
      storage.setItem(key, JSON.stringify(values));
      return values[signature];
    },
    prepare(action, payload) {
      const values = pending();
      const name = signature(action, payload);
      if (!values[name]) values[name] = { ...payload, command_id: this.get(action, payload) };
      storage.setItem(pendingKey, JSON.stringify(values));
      return values[name];
    },
    settle(action, payload) {
      const values = pending();
      const completed = values[signature(action, payload)]?.command_id;
      const ids = JSON.parse(storage.getItem(key) || '{}');
      for (const [name, value] of Object.entries(ids)) if (value === completed) delete ids[name];
      storage.setItem(key, JSON.stringify(ids));
      delete values[signature(action, payload)];
      storage.setItem(pendingKey, JSON.stringify(values));
    },
  };
}
