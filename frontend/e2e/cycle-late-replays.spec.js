import { test, expect } from '@playwright/test';

async function prepare(page, { admin = true, fail = false } = {}) {
  await page.addInitScript(() => localStorage.setItem('language', 'ru'));
  const battle = { id: 1, cycle_id: 1, territory_id: 2, territory_name: 'Земля проверки',
    completed_at: '2026-10-17T00:05:00Z', winner_clan_id: 1, recalculated_winner_clan_id: 1,
    adjustments: [], contributions: [], sides: [
      { clan_id: 1, clan_name: 'Первый клан', score: '100', role: 'defense',
        members: [{ user_id: 3, username: 'Старое имя', display_name: 'Новое имя Арены' }] },
      { clan_id: 2, clan_name: 'Второй клан', score: '0', role: 'attack', members: [] },
    ] };
  let failed = fail;
  const seen = [];
  await page.route('**/api/v1/**', route => {
    const url = new URL(route.request().url());
    const path = url.pathname;
    let json = {};
    if (path.endsWith('/auth/session') || path.endsWith('/users/me')) {
      json = { id: 1, username: 'Проверяющий', language: 'ru', is_verified: true,
        is_claimed: true, role: { name: admin ? 'admin' : 'user' }, onboarding_completed: true };
    } else if (path === '/api/v1/campaign/cycles/1') {
      json = { id: 1, number: 1, phase: 'rest', battle_at: '2026-10-15T00:00:00Z',
        battle_ends_at: '2026-10-17T00:00:00Z', replay_deadline: '2026-10-17T00:05:00Z' };
    } else if (path.endsWith('/cycles/1/battles')) json = { battles: [battle] };
    else if (path.endsWith('/cycles/battles/1')) json = battle;
    else if (path.endsWith('/late-replays')) {
      seen.push(url.searchParams.get('after_id'));
      if (failed) { failed = false; return route.fulfill({ status: 503, json: { detail: 'Временная ошибка' } }); }
      json = url.searchParams.get('after_id') === '8' ? { items: [{
        match_id: 9, replay_id: 'bfmeladder:late-replay', source_replay_id: 'late-replay',
        started_at: '2026-10-16T12:00:00Z', finished_at: '2026-10-16T12:10:00Z',
        historical_elo_available: false, players: [{ user_id: 3, clan_id: 1, display_name: 'Новое имя Арены', reason: null }],
      }], scanned: 1, next_after_id: null } : { items: [], scanned: 8, next_after_id: 8 };
    } else if (path.includes('localization')) json = [];
    else if (path.includes('notifications')) json = { items: [], unread_count: 0 };
    else if (path.includes('presence')) json = { items: [] };
    else if (path.includes('clans/my')) return route.fulfill({ status: 404, json: { detail: 'Нет клана' } });
    return route.fulfill({ json });
  });
  await page.goto('/campaign/cycles/1?territory=2');
  await expect(page.locator('.cycle-detail')).toBeVisible();
  if (admin) await page.getByRole('tab', { name: /Управление/ }).click();
  return seen;
}

for (const width of [390, 1440]) {
  test(`Администратор находит поздний матч без автоматического начисления при ширине ${width}`, async ({ page }, testInfo) => {
    await page.setViewportSize({ width, height: 1000 });
    const seen = await prepare(page);
    const changes = [];
    page.on('request', request => { if (request.method() === 'POST') changes.push(request.url()); });
    await page.getByRole('tab', { name: /Составы/ }).click();
    await expect(page.locator('.cycle-lineups')).toContainText('Новое имя Арены');
    await page.getByRole('tab', { name: /Управление/ }).click();
    const panel = page.getByRole('region', { name: 'Пропущенные матчи' });
    await panel.getByRole('button', { name: 'Проверить матчи', exact: true }).click();
    await expect(panel.getByText('Пропущенных матчей не найдено', { exact: true })).toHaveCount(0);
    await panel.getByRole('button', { name: 'Проверить следующие матчи', exact: true }).click();
    await expect(panel).toContainText('Новое имя Арены');
    await expect(panel).toContainText('Не подтверждён Elo на момент матча');
    await expect(panel.getByRole('link', { name: 'Открыть реплей' })).toHaveAttribute('href',
      'https://bfmeladder.com/replay/late-replay');
    expect(seen).toEqual(['0', '8']);
    expect(changes).toEqual([]);
    await expect(page.locator('.cycle-clan-card')).toHaveCount(0);
    expect(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth + 1)).toBe(false);
    await panel.screenshot({ path: testInfo.outputPath('late-replays.png') });
  });
}

test('Обычный участник не видит административную проверку и не запрашивает её', async ({ page }) => {
  const seen = await prepare(page, { admin: false });
  await expect(page.getByRole('region', { name: 'Пропущенные матчи' })).toHaveCount(0);
  expect(seen).toEqual([]);
});

test('Ошибка не продвигает страницу и допускает безопасный повтор', async ({ page }) => {
  const seen = await prepare(page, { fail: true });
  const panel = page.getByRole('region', { name: 'Пропущенные матчи' });
  await panel.getByRole('button', { name: 'Проверить матчи', exact: true }).click();
  await expect(panel.getByRole('alert')).toBeVisible();
  await panel.getByRole('button', { name: 'Проверить матчи', exact: true }).click();
  await expect(panel.getByRole('button', { name: 'Проверить следующие матчи', exact: true })).toBeVisible();
  expect(seen).toEqual(['0', '0']);
});

for (const width of [390, 1440]) {
  test(`Поздний матч принимается только после просмотра и подтверждения при ${width}px`, async ({ page }, testInfo) => {
    await page.setViewportSize({ width, height: 1000 });
    await prepare(page);
    const requests = [];
    await page.route('**/api/v1/campaign/cycles/battles/1/late-replays/9', route => {
      if (route.request().method() === 'GET') return route.fulfill({ json: {
        match_id: 9, replay_id: 'bfmeladder:late-replay', preview_token: 'a'.repeat(64), can_accept: true,
        players: [{ user_id: 3, clan_id: 1, display_name: 'Новое имя Арены', points: '100',
          reason: 'counted', calculation: { historical_elo: '1500', base_points: '100',
            victory_bonus_percent: '0', direct_multiplier: 1, exhaustion_multiplier: '1' } }],
      } });
      requests.push(route.request().postDataJSON());
      return route.fulfill({ json: { id: 1, cycle_id: 1, territory_id: 2,
        completed_at: '2026-10-17T00:05:00Z', sides: [], contributions: [], adjustments: [],
        winner_clan_id: 1, recalculated_winner_clan_id: 1 } });
    });
    const panel = page.getByRole('region', { name: 'Пропущенные матчи' });
    await panel.getByRole('button', { name: 'Проверить матчи', exact: true }).click();
    await panel.getByRole('button', { name: 'Проверить следующие матчи', exact: true }).click();
    await panel.getByRole('button', { name: 'Рассмотреть матч', exact: true }).click();
    await expect(panel).toContainText('1500');
    await expect(panel.getByText('Не подтверждён Elo на момент матча', { exact: true })).toHaveCount(0);
    const submit = panel.getByRole('button', { name: 'Сохранить решение', exact: true });
    await expect(submit).toBeDisabled();
    await panel.getByLabel('Причина решения').fill('Пропущен при недоступности сервера');
    await panel.getByRole('checkbox', { name: 'Подтверждаю решение без автоматической смены владельца' }).check();
    await panel.screenshot({ path: testInfo.outputPath('late-review-form.png') });
    await submit.click();
    expect(requests).toHaveLength(1);
    expect(requests[0]).toMatchObject({ counted: true, preview_token: 'a'.repeat(64),
      reason: 'Пропущен при недоступности сервера' });
    await expect(panel.getByRole('button', { name: 'Рассмотреть матч' })).toHaveCount(0);
    expect(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth + 1)).toBe(false);
  });
}

test('Без исторического Elo можно только отклонить; повтор после ошибки сохраняет ключ команды', async ({ page }) => {
  await prepare(page);
  const requests = [];
  await page.route('**/api/v1/campaign/cycles/battles/1/late-replays/9', route => {
    if (route.request().method() === 'GET') return route.fulfill({ json: {
      match_id: 9, preview_token: 'b'.repeat(64), can_accept: false,
      players: [{ user_id: 3, clan_id: 1, display_name: 'Игрок без Elo', points: '0',
        reason: 'missing_historical_elo', calculation: {} }],
    } });
    requests.push(route.request().postDataJSON());
    if (requests.length === 1) return route.fulfill({ status: 503, json: { detail: 'Повторите запрос' } });
    return route.fulfill({ json: { id: 1, cycle_id: 1, territory_id: 2,
      completed_at: '2026-10-17T00:05:00Z', sides: [], contributions: [], adjustments: [] } });
  });
  const panel = page.getByRole('region', { name: 'Пропущенные матчи' });
  await panel.getByRole('button', { name: 'Проверить матчи', exact: true }).click();
  await panel.getByRole('button', { name: 'Проверить следующие матчи', exact: true }).click();
  await panel.getByRole('button', { name: 'Рассмотреть матч', exact: true }).click();
  await expect(panel.getByRole('option', { name: 'Засчитать', exact: true })).toHaveAttribute('disabled', '');
  await expect(panel.getByLabel('Решение по матчу')).toHaveValue('false');
  await panel.getByLabel('Причина решения').fill('Нет подтверждённого рейтинга');
  await panel.getByRole('checkbox').check();
  await panel.getByRole('button', { name: 'Сохранить решение', exact: true }).click();
  await expect(panel.getByRole('alert')).toBeVisible();
  await panel.getByRole('button', { name: 'Сохранить решение', exact: true }).click();
  await expect(panel.getByRole('button', { name: 'Рассмотреть матч' })).toHaveCount(0);
  expect(requests).toHaveLength(2);
  expect(requests[0]).toEqual(requests[1]);
  expect(requests[0].counted).toBe(false);
});
