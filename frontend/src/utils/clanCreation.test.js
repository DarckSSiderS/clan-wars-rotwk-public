import assert from 'node:assert/strict';
import test from 'node:test';

import {
  getClanCreationSubmitAction,
  getClanMapPreviewSource,
  getContrastingClanColor,
  validateClanCreationDetails,
  validateClanImageFile,
} from './clanCreation.js';


test('контрастный цвет остаётся одинаковым для формы и карты', () => {
  assert.equal(getContrastingClanColor('#f2d66d'), '#24170f');
  assert.equal(getContrastingClanColor('#1e6fb9'), '#f3dfb0');
});


test('проверка изображения отклоняет большой и неподдерживаемый файл', () => {
  assert.equal(
    validateClanImageFile({ size: 5 * 1024 * 1024 + 1, type: 'image/png' }),
    'too_large',
  );
  assert.equal(
    validateClanImageFile({ size: 128, type: 'text/plain' }),
    'unsupported_type',
  );
  assert.equal(
    validateClanImageFile({ size: 128, type: 'image/webp' }),
    null,
  );
});

test('первый шаг требует заполнить название клана', () => {
  const translate = (_key, fallback) => fallback;

  assert.deepEqual(validateClanCreationDetails({ name: '   ' }, translate), {
    name: 'Название клана обязательно',
  });
  assert.deepEqual(validateClanCreationDetails({ name: 'Стражи Севера' }, translate), {});
});

test('предпросмотр территории выбирает эмблему раньше аватарки', () => {
  assert.equal(getClanMapPreviewSource('/emblem.webp', '/avatar.webp'), '/emblem.webp');
  assert.equal(getClanMapPreviewSource(null, '/avatar.webp'), '/avatar.webp');
  assert.equal(getClanMapPreviewSource(null, null), null);
});

test('отправка формы на первом шаге продолжает настройку, а на втором создаёт клан', () => {
  assert.equal(getClanCreationSubmitAction(1), 'continue');
  assert.equal(getClanCreationSubmitAction(2), 'submit');
});
