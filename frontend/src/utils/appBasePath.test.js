import { describe, it } from 'node:test';
import assert from 'node:assert/strict';
import { withAppBase, publicAssetCredentials } from './appBasePath.js';

describe('адреса изолированного предпросмотра', () => {
  it('обычная сборка сохраняет существующие адреса', () => {
    assert.equal(withAppBase('/api/v1/users/me', '/'), '/api/v1/users/me');
  });
  it('API и публичные загрузки получают отдельный префикс', () => {
    assert.equal(withAppBase('/api/v1/users/me', '/admin/preview/'), '/admin/preview/api/v1/users/me');
    assert.equal(withAppBase('/encyclopedia/ennorath/catalog.json', '/admin/preview/'), '/admin/preview/encyclopedia/ennorath/catalog.json');
  });
  it('не добавляет повторный префикс и не переписывает внешние адреса', () => {
    assert.equal(withAppBase('/admin/preview/api/v1/test', '/admin/preview/'), '/admin/preview/api/v1/test');
    assert.equal(withAppBase('https://example.com/a', '/admin/preview/'), 'https://example.com/a');
  });
  it('закрытые карта и каталог передают cookie только своему шлюзу', () => {
    assert.equal(publicAssetCredentials('/map-interactive.svg', '/admin/preview/'), 'same-origin');
    assert.equal(publicAssetCredentials('/encyclopedia/ennorath/catalog.json', '/admin/preview/'), 'same-origin');
  });
  it('обычная сборка и внешние ресурсы не получают cookie', () => {
    assert.equal(publicAssetCredentials('/map-interactive.svg', '/'), 'omit');
    assert.equal(publicAssetCredentials('https://example.com/a', '/admin/preview/'), 'omit');
    assert.equal(publicAssetCredentials('//example.com/a', '/admin/preview/'), 'omit');
  });
});
