const CYRILLIC_PATTERN = /[А-Яа-яЁё]/u;

const TITLE_KEYS = {
  achievement_completed: 'notification_achievement_completed',
  feedback_created: 'notification_feedback_created',
  feedback_reply: 'notification_feedback_reply',
  feedback_status: 'notification_feedback_status',
  clan_trader_changed: 'notification_clan_trader_changed',
  clan_relic_loadout_changed: 'notification_clan_relic_loadout_changed',
  clan_relic_purchased: 'notification_clan_relic_purchased',
  clan_role_changed: 'notification_clan_role_changed',
  clan_warlord_changed: 'notification_clan_warlord_changed',
  clan_invite: 'notification_clan_invite',
  clan_application: 'notification_clan_application',
  clan_invite_response: 'notification_clan_invite_response',
  clan_application_response: 'notification_clan_application_response',
  clan_member_kicked: 'notification_clan_member_kicked',
  diplomacy: 'notification_diplomacy',
  clan_trade_started: 'notification_clan_trade_started',
  clan_trade_completed: 'notification_clan_trade_completed',
  online_request: 'notification_online_request',
  direct_message: 'notification_direct_message',
  shop_purchase: 'notification_shop_purchase',
  war_started: 'notification_war_started',
  war_completed: 'notification_war_completed',
};

const localizedOrFallback = (value, fallbackKey, t) => {
  const text = String(value || '').trim();
  if (text && !CYRILLIC_PATTERN.test(text)) return text;
  return t(fallbackKey);
};

export const getNotificationPresentation = (notification, language, t) => {
  const titleKey = TITLE_KEYS[notification?.notification_type];
  if (language === 'ru') {
    return {
      title: notification?.title || t(titleKey || 'notification_generic'),
      message: notification?.message || t('notification_open_details'),
    };
  }

  return {
    title: titleKey
      ? t(titleKey)
      : localizedOrFallback(notification?.title, 'notification_generic', t),
    message: localizedOrFallback(notification?.message, 'notification_open_details', t),
  };
};

export default getNotificationPresentation;
