import assert from 'node:assert/strict';
import test from 'node:test';

import { getNotificationPresentation } from './notificationPresentation.js';

const text = {
  notification_clan_invite: ['Приглашение в клан', 'Clan invitation', 'Clan-Einladung'],
  notification_generic: ['Новое уведомление', 'New notification', 'Neue Benachrichtigung'],
  notification_open_details: ['Откройте связанный раздел, чтобы узнать подробности.', 'Open the linked section for details.', 'Öffne den verknüpften Bereich für Details.'],
};

const translator = (language) => (key) => text[key][['ru', 'en', 'de'].indexOf(language)];

test('keeps detailed server copy in Russian', () => {
  const notification = {
    notification_type: 'clan_invite',
    title: 'Приглашение от клана',
    message: 'Клан «Гондор» приглашает вас.',
  };
  assert.deepEqual(getNotificationPresentation(notification, 'ru', translator('ru')), {
    title: notification.title,
    message: notification.message,
  });
});

test('replaces Russian server copy in English and German', () => {
  const notification = {
    notification_type: 'clan_invite',
    title: 'Приглашение от клана',
    message: 'Клан «Гондор» приглашает вас.',
  };
  assert.deepEqual(getNotificationPresentation(notification, 'en', translator('en')), {
    title: 'Clan invitation',
    message: 'Open the linked section for details.',
  });
  assert.deepEqual(getNotificationPresentation(notification, 'de', translator('de')), {
    title: 'Clan-Einladung',
    message: 'Öffne den verknüpften Bereich für Details.',
  });
});

test('preserves already localized copy for an unknown notification type', () => {
  const notification = {
    notification_type: 'future_event',
    title: 'Maintenance complete',
    message: 'The service is available again.',
  };
  assert.deepEqual(getNotificationPresentation(notification, 'en', translator('en')), {
    title: notification.title,
    message: notification.message,
  });
});
