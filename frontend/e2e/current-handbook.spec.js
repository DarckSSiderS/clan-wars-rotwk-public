import { test, expect } from '@playwright/test';

async function mockRules(page, { failure = false, guide = true } = {}) {
  await page.addInitScript(() => localStorage.setItem('language', 'ru'));
  await page.route('**/api/v1/**', route => {
    const url = new URL(route.request().url());
    if (url.pathname === '/api/v1/campaign/rules/public') {
      if (failure) return route.fulfill({ status: 503, json: { detail: 'Недоступно' } });
      const selected = url.searchParams.get('season_id');
      return route.fulfill({ json: {
        mechanics_version: selected === '2' ? 'cycle_v1' : null,
        season: selected ? { id: Number(selected), name: selected === '1' ? 'Первый сезон' : 'Активный сезон' } : null,
        rule_set: { version: 5, complete: true, values: {} },
        ...(!selected && guide ? { guide: { mechanics_version: 'cycle_v1', status: 'upcoming', previous_season_id: 1 } } : {}),
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
  test(`Текущий справочник межсезонья и исторические правила: ${width}`, async ({ page }, testInfo) => {
    await page.setViewportSize({ width, height: 900 });
    const errors = [];
    page.on('pageerror', error => errors.push(error.message));
    await mockRules(page);
    await page.goto('/rules');
    await expect(page.getByRole('heading', { level: 1 })).toHaveText('Справочник циклов клановой войны');
    await expect(page.getByRole('heading', { level: 2 })).toHaveText('Межсезонье: новый сезон ещё не запущен');
    const panel = page.getByRole('tabpanel');
    await expect(panel).toContainText('после запуска нового сезона');
    await expect(panel.getByRole('link', { name: 'Архив завершённого сезона' })).toHaveAttribute('href', '/seasons/1');
    await expect(panel.getByRole('link', { name: 'Исторические правила сезона' })).toHaveAttribute('href', '/rules?season=1');
    await page.screenshot({ path: testInfo.outputPath(`interseason-${width}.png`), fullPage: true });

    for (const [name, content] of [
      [/Планирование/, 'Защитный шаблон'], [/Разведка/, 'разведчика'],
      [/Запас и помощь/, 'N+3'], [/Очки и исход/, '−50 + d/16'],
      [/Реликвии/, 'четырёх'], [/Обмен и караваны/, '120 золота'],
    ]) {
      await page.getByRole('tab', { name }).click();
      await expect(panel).toContainText(content);
      await expect(panel).toContainText('после запуска');
      expect(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth + 1)).toBe(false);
    }
    await page.getByRole('tab', { name: /Обмен и караваны/ }).press('Home');
    await expect(page.getByRole('tab', { name: /Межсезонье/ })).toHaveAttribute('aria-selected', 'true');
    await panel.getByRole('link', { name: 'Исторические правила сезона' }).click();
    await expect(page.getByRole('heading', { level: 1 })).toHaveText('Справочник мира ClanWars');
    await expect(page.getByRole('tab', { name: /Перехват/ })).toHaveCount(0);
    await page.getByRole('tab', { name: /Подготовка войны/ }).click();
    await expect(page).toHaveURL(/season=1/);
    await page.screenshot({ path: testInfo.outputPath(`legacy-${width}.png`), fullPage: true });
    await page.goBack();
    await expect(page.getByRole('heading', { level: 2 })).toHaveText('Межсезонье: новый сезон ещё не запущен');
    expect(errors).toEqual([]);
  });
}

test('Без подтверждения и при ошибке будущие правила не показываются как действующие', async ({ page }) => {
  await mockRules(page, { failure: true });
  await page.goto('/rules');
  await expect(page.getByRole('status')).toContainText('временно не загрузились');
  await expect(page.getByRole('heading', { level: 1 })).toHaveText('Справочник мира ClanWars');
  await page.unroute('**/api/v1/**');
  await mockRules(page, { guide: false });
  await page.reload();
  await expect(page.getByRole('tab', { name: /Перехват/ })).toHaveCount(0);
});

test('Явно выбранный циклический сезон сохраняет собственный контекст', async ({ page }) => {
  await mockRules(page);
  await page.goto('/rules?season=2&section=attacks');
  await expect(page.getByRole('heading', { level: 1 })).toHaveText('Справочник циклов клановой войны');
  await expect(page.getByRole('tabpanel')).toContainText('Активный сезон');
  await expect(page.getByRole('tabpanel')).not.toContainText('Межсезонье');
  await page.getByRole('tab', { name: /Разведка/ }).click();
  await expect(page).toHaveURL(/season=2&section=scouting/);
});

test('Старая ссылка на личный прогресс остаётся доступна в новом справочнике', async ({ page }) => {
  await mockRules(page);
  await page.goto('/rules?section=progress');
  await expect(page.getByRole('tabpanel')).toContainText('Личный профиль и прогресс');
  await expect(page).toHaveURL(/section=progress/);
});
