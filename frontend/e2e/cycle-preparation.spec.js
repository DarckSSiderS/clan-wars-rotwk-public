import { test, expect } from '@playwright/test';
async function setupScouting(page, { post, scout = {} } = {}) {
  const data = { cycle_id: 1, clan_id: 7, clan_name: 'Akatsuki', territories: [{ id: 10, name: 'Home' }],
    scout: { price: '200', cutoff: '2099-01-01T00:00:00Z', can_request: true, wallet_revision: 1,
      players: [{ user_id: 42, name: 'Новое имя', external_uuid: 'arena-42' }, { user_id: 43, name: 'Новое имя', external_uuid: 'arena-43' }], request: null, report: null, ...scout }, startup: { ready: false, can_claim: false } };
  const commands = [];
  await page.addInitScript(() => localStorage.setItem('language', 'ru'));
  await page.route('**/api/v1/**', async route => {
    const path = new URL(route.request().url()).pathname;
    let payload = {};
    if (path.endsWith('/auth/session') || path.endsWith('/users/me')) payload = { id: 1, username: 'Head', language: 'ru', is_claimed: true, is_verified: true, role: { name: 'user' }, onboarding_completed: true };
    else if (path.endsWith('/clans/my')) payload = { id: 7 };
    else if (path.endsWith('/preparation')) payload = data;
    else if (path.endsWith('/scout')) {
      commands.push(route.request().postDataJSON());
      if (post) return post(route, data);
      data.scout.can_request = false;
      data.scout.request = { id: 1, territory_id: 10, scout_user_id: 43, scout_name: 'Новое имя', scout_uuid: 'arena-43' }; data.scout.report = { enemy_squads: [3, 1] }; payload = data.scout.request;
    } else if (path.includes('notifications')) payload = { items: [], unread_count: 0, total: 0 };
    else if (path.includes('presence')) payload = { items: [] };
    else if (path.includes('localization')) payload = [];
    return route.fulfill({ json: payload });
  });
  await page.goto('/campaign/cycles/1/preparation');
  return { data, commands };
}

test('a preserved scouting order without a player never displays a null identity or a false player lock', async ({ page }) => {
  const { commands } = await setupScouting(page, { scout: { can_request: false,
    request: { id: 1, territory_id: 10, scout_user_id: null, scout_uuid: null }, report: { enemy_squads: [] } } });
  await expect(page.locator('.cycle-scouting')).toContainText('Разведка заказана без назначения игрока.');
  await expect(page.locator('.cycle-scouting')).not.toContainText('#null');
  await expect(page.locator('.cycle-scouting')).not.toContainText('Разведчик закреплён до конца цикла');
  expect(commands).toEqual([]);
});

for (const width of [390, 1440]) {
test(`scouting has a fixed paid scout and an anonymous numeric report at ${width}px`, async ({ page }) => {
  await page.setViewportSize({ width, height: 1000 });
  const { commands } = await setupScouting(page);
  await page.getByRole('combobox', { name: 'Цель разведки', exact: true }).selectOption('10');
  await expect(page.getByRole('button', { name: 'Заказать разведку', exact: true })).toBeDisabled();
  await page.getByRole('combobox', { name: 'Разведчик', exact: true }).selectOption('43');
  await page.getByRole('button', { name: 'Заказать разведку', exact: true }).click();
  await expect(page.getByRole('dialog')).toContainText('200');
  await expect(page.getByRole('dialog')).toContainText('Новое имя');
  await expect(page.getByRole('dialog')).toContainText('до конца цикла');
  await expect(page.locator('.MuiDialog-container')).toHaveCSS('opacity', '1');
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await page.screenshot({ path: `test-results/cycle-scout-confirm-${width}.png`, fullPage: true });
  await page.getByRole('dialog').getByRole('button', { name: 'Подтвердить', exact: true }).click();
  await expect(page.locator('.cp-report')).toContainText('3');
  await expect(page.locator('.cp-report')).toContainText('1');
  expect(commands).toEqual([{ territory_id: 10, scout_user_id: 43, expected_revision: 1 }]);
  await expect(page.locator('.cycle-scouting')).toContainText('Новое имя');
  await expect(page.locator('.cycle-scouting')).toContainText('до конца цикла');
  await expect(page.getByRole('combobox', { name: 'Разведчик', exact: true })).toHaveCount(0);
  await expect(page.getByRole('button', { name: 'Заказать разведку' })).toHaveCount(0);
  await expect(page.locator('.MuiDialog-root')).toHaveCount(0);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await page.screenshot({ path: `test-results/cycle-scout-report-${width}.png`, fullPage: true });
});
}

test('repeated scout confirmation sends only one command while payment is pending', async ({ page }) => {
  let release;
  const gate = new Promise(resolve => { release = resolve; });
  const { commands } = await setupScouting(page, { post: async (route, data) => {
    await gate;
    data.scout.can_request = false;
    data.scout.request = { territory_id: 10, scout_user_id: 43, scout_name: 'Новое имя', scout_uuid: 'arena-43' };
    return route.fulfill({ json: data.scout.request });
  } });
  await page.getByRole('combobox', { name: 'Цель разведки', exact: true }).selectOption('10');
  await page.getByRole('combobox', { name: 'Разведчик', exact: true }).selectOption('43');
  await page.getByRole('button', { name: 'Заказать разведку', exact: true }).click();
  const confirm = page.getByRole('dialog').getByRole('button', { name: 'Подтвердить', exact: true });
  await confirm.evaluate(button => { button.click(); button.click(); });
  await expect.poll(() => commands.length).toBe(1);
  await expect(confirm).toBeDisabled();
  await expect(page.getByRole('dialog').getByRole('button', { name: 'Отмена', exact: true })).toBeDisabled();
  release();
  await expect(page.getByRole('dialog')).toHaveCount(0);
  await expect(page.locator('.cycle-scouting')).toContainText('Новое имя');
  expect(commands).toEqual([{ territory_id: 10, scout_user_id: 43, expected_revision: 1 }]);
});

test('conflicting scout payment reloads eligibility and requires a fresh selection', async ({ page }) => {
  const { commands } = await setupScouting(page, { post: (route, data) => {
    data.scout.wallet_revision = 2;
    data.scout.players = data.scout.players.filter(player => player.user_id !== 43);
    return route.fulfill({ status: 409, json: { detail: 'Scout no longer free' } });
  } });
  await page.getByRole('combobox', { name: 'Цель разведки', exact: true }).selectOption('10');
  await page.getByRole('combobox', { name: 'Разведчик', exact: true }).selectOption('43');
  await page.getByRole('button', { name: 'Заказать разведку', exact: true }).click();
  await page.getByRole('dialog').getByRole('button', { name: 'Подтвердить', exact: true }).click();
  await expect(page.getByRole('dialog')).toHaveCount(0);
  await expect(page.getByRole('alert')).toBeVisible();
  const scout = page.getByRole('combobox', { name: 'Разведчик', exact: true });
  await expect(scout).toHaveValue('');
  await expect(scout.locator('option[value="43"]')).toHaveCount(0);
  await expect(page.getByRole('button', { name: 'Заказать разведку', exact: true })).toBeDisabled();
  expect(commands).toEqual([{ territory_id: 10, scout_user_id: 43, expected_revision: 1 }]);
});

test('preparation explains that an assigned player must be freed before scouting', async ({ page }) => {
  const { commands } = await setupScouting(page, { scout: { can_request: false, players: [], unavailable_reason: 'no_free_players' } });
  await expect(page.locator('.cycle-scouting')).toContainText('Нет свободного игрока');
  await expect(page.locator('.cycle-scouting')).toContainText('назначение в отрядах');
  await expect(page.getByRole('button', { name: 'Заказать разведку', exact: true })).toHaveCount(0);
  expect(commands).toEqual([]);
});

test('starting land release is previewed before the immutable claim', async ({ page }) => {
  const lands = [{ id: 10, name: 'Home', owner_clan_id: 7 }, { id: 11, name: 'North', owner_clan_id: null },
    { id: 12, name: 'East', owner_clan_id: null }, { id: 13, name: 'Released', owner_clan_id: 7 }];
  const data = { cycle_id: 1, clan_id: 7, clan_name: 'Akatsuki', territories: lands,
    scout: { can_request: false, cutoff: '2099-01-01T00:00:00Z' },
    startup: { ready: true, can_claim: true, revision: 1, deadline: '2099-01-01T00:00:00Z', selected_lands: [] } };
  const commands = [];
  await page.addInitScript(() => localStorage.setItem('language', 'ru'));
  await page.route('**/api/v1/**', route => {
    const path = new URL(route.request().url()).pathname;
    let payload = {};
    if (path.endsWith('/auth/session') || path.endsWith('/users/me')) payload = { id: 1, username: 'Head', language: 'ru', is_claimed: true, is_verified: true, role: { name: 'user' }, onboarding_completed: true };
    else if (path.endsWith('/clans/my')) payload = { id: 7 };
    else if (path.endsWith('/preparation')) payload = data;
    else if (path.endsWith('/startup/preview')) { commands.push('preview'); payload = { selected: [10, 11, 12], release: [13] }; }
    else if (path.endsWith('/startup/claim')) { commands.push(route.request().postDataJSON()); data.startup.can_claim = false; data.startup.selected_lands = [10, 11, 12]; }
    else if (path.includes('notifications')) payload = { items: [], unread_count: 0, total: 0 };
    else if (path.includes('presence')) payload = { items: [] };
    else if (path.includes('localization')) payload = [];
    return route.fulfill({ json: payload });
  });
  await page.goto('/campaign/cycles/1/preparation');
  for (const name of ['Home', 'North', 'East']) await page.getByRole('checkbox', { name, exact: true }).check();
  await page.getByRole('button', { name: 'Проверить выбор', exact: true }).click();
  await expect(page.getByRole('dialog')).toContainText('Released');
  expect(commands).toEqual(['preview']);
  await page.getByRole('dialog').getByRole('button', { name: 'Подтвердить', exact: true }).click();
  await expect.poll(() => commands.length).toBe(2);
  expect(commands[1]).toEqual({ selected: [10, 11, 12], expected_revision: 1 });
});
