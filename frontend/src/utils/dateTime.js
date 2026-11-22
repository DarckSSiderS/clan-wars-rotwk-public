export const CAMPAIGN_TIME_ZONE = 'Europe/Moscow';

export const asUtcIsoTime = value => typeof value === 'string'
  && /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(?::\d{2}(?:\.\d+)?)?$/.test(value) ? value + 'Z' : value;

const localeCode = (locale) => ({ ru: 'ru-RU', en: 'en-GB', de: 'de-DE', eng: 'en-GB' }[locale] || locale || 'ru-RU');
const moscowTimeLabel = (locale) => (localeCode(locale) === 'ru-RU' ? 'МСК' : 'MSK');

export const formatMoscowDateTime = (value, fallback = '', locale = 'ru') => {
  if (!value) return fallback;
  const formatted = new Date(value).toLocaleString(localeCode(locale), {
    timeZone: CAMPAIGN_TIME_ZONE,
    day: '2-digit',
    month: '2-digit',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  });
  return `${formatted} ${moscowTimeLabel(locale)}`;
};

export const formatMoscowDate = (value, fallback = '', locale = 'ru') => {
  if (!value) return fallback;
  return new Date(value).toLocaleDateString(localeCode(locale), {
    timeZone: CAMPAIGN_TIME_ZONE,
    day: '2-digit',
    month: '2-digit',
    year: 'numeric',
  });
};

export const formatMoscowTime = (value, fallback = '', locale = 'ru') => {
  if (!value) return fallback;
  const formatted = new Date(value).toLocaleTimeString(localeCode(locale), {
    timeZone: CAMPAIGN_TIME_ZONE,
    hour: '2-digit',
    minute: '2-digit',
  });
  return `${formatted} ${moscowTimeLabel(locale)}`;
};
