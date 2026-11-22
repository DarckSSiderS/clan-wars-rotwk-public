import { test, expect } from '@playwright/test';

async function mockHandbook(page, failure = false) {
  await page.addInitScript(() => localStorage.setItem('language', 'ru'));
  await page.route('**/api/v1/**', route => {
    const url = new URL(route.request().url());
    if (url.pathname === '/api/v1/campaign/rules/public') {
      if (failure) return route.fulfill({ status: 503, json: { detail: 'Источник временно недоступен' } });
      const cycle = url.searchParams.get('season_id') === '2';
      return route.fulfill({ json: {
        mechanics_version: cycle ? 'cycle_v1' : null,
        season: { id: cycle ? 2 : 1, name: cycle ? 'Проверка циклов' : 'Прежняя кампания' },
        rule_set: { version: 2, complete: true, values: {} },
      } });
    }
    if (url.pathname.includes('localization')) return route.fulfill({ json: [] });
    if (url.pathname.includes('notifications')) return route.fulfill({ json: { items: [], unread_count: 0 } });
    if (url.pathname.includes('presence')) return route.fulfill({ json: { items: [] } });
    if (url.pathname.includes('clans/my')) return route.fulfill({ status: 404, json: { detail: 'Нет клана' } });
    if (url.pathname.includes('auth/session') || url.pathname.endsWith('/users/me')) {
      return route.fulfill({ status: 401, json: { detail: 'Не авторизован' } });
    }
    return route.fulfill({ json: {} });
  });
}

for (const width of [1440, 390]) {
  test(`Справочник циклов: навигация и читаемость при ширине ${width}`, async ({ page }, testInfo) => {
    await page.setViewportSize({ width, height: 900 });
    const errors = [];
    page.on('pageerror', error => errors.push(error.message));
    await mockHandbook(page);
    await page.goto('/rules?season=2');
    await expect(page.getByRole('heading', { level: 1 })).toHaveText('Справочник циклов клановой войны');
    await expect(page.getByRole('tab')).toHaveCount(18);
    await page.getByRole('tab', { name: /Запас и помощь/ }).click();
    await expect(page.getByRole('tabpanel')).toContainText('24 часа');
    await page.getByRole('tab', { name: /Перехват/ }).click();
    await expect(page.getByRole('heading', { level: 2 })).toHaveText('Засада на пути подкрепления');
    await expect(page.getByRole('tab', { name: /Перехват/ })).toBeInViewport({ ratio: 0.8 });
    if (width === 390) {
      await page.setViewportSize({ width: 320, height: 900 });
      await expect(page.getByRole('tab', { name: /Перехват/ })).toBeInViewport({ ratio: 0.8 });
      await page.setViewportSize({ width, height: 900 });
      await expect(page.getByRole('tab', { name: /Перехват/ })).toBeInViewport({ ratio: 0.8 });
    }
    await page.screenshot({ path: testInfo.outputPath('cycle-handbook.png') });
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth > window.innerWidth + 1);
    expect(overflow).toBe(false);
    await page.getByRole('tab', { name: /Перехват/ }).press('End');
    await expect(page.getByRole('tab', { name: /Частые вопросы/ })).toHaveAttribute('aria-selected', 'true');
    await expect(page.getByRole('tab', { name: /Частые вопросы/ })).toBeInViewport({ ratio: 0.8 });
    await page.goto('/rules?season=1');
    await expect(page.getByRole('heading', { level: 1 })).toHaveText('Справочник мира ClanWars');
    await expect(page.getByRole('tab', { name: /Перехват/ })).toHaveCount(0);
    expect(errors).toEqual([]);
  });
}

test('Ошибка загрузки не выдаёт новые правила за действующие', async ({ page }) => {
  await mockHandbook(page, true);
  await page.goto('/rules?season=2');
  await expect(page.getByRole('status')).toContainText('временно не загрузились');
  await expect(page.getByRole('heading', { level: 1 })).toHaveText('Справочник мира ClanWars');
  await expect(page.getByRole('tab', { name: /Перехват/ })).toHaveCount(0);
});
