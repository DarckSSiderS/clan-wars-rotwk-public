import { test, expect } from '@playwright/test';

const wallet = { gold: '10000', iron: '1000', wood: '1000', food: '1000', mithril: '100' };
const price = { gold: '3000', iron: '15', wood: '25', food: '20', mithril: '4' };
const economy = () => ({
  season_id: 1, cycle_id: 7, clan_id: 11, clan_name: 'Own clan', ready: true,
  can_manage: true, can_select: true, can_trade: true,
  state: { revision: 1, wallet, relics: { white_tree: 1 }, active_relics: [], starters_chosen: true },
  catalog: [{ key: 'white_tree', name: 'Знамя Белого Древа', effect: 'gold', effects: ['15', '25', '35'], costs: [price, price, price] }],
  market_buy: { iron: '45', wood: '40', food: '30', mithril: '300' },
  market_sell: { iron: '10', wood: '8', food: '6', mithril: '60' },
  lands: [{ territory_id: 10, name: 'Home', revision: 0, quotes: { gold: { level: 0, next_effect: '35', cost: { gold: '300', iron: '5', wood: '10', food: '5', mithril: '0' } } } }],
});

async function mockClan(page, { data = economy(), mode = 'cycle_v1', foreign = false, member = false, anonymous = false, noCycle = false, navigationError = false } = {}) {
  const user = { id: 1, username: 'Head', language: 'ru', is_verified: true, is_claimed: true, role: { name: 'user' }, onboarding_completed: true };
  const clan = { id: 11, name: 'Own clan', leader_id: foreign || member ? 2 : 1, created_at: '2026-01-01T00:00:00Z', member_count: 1 };
  const requests = [], writes = [];
  await page.setViewportSize({ width: 1440, height: 1000 });
  await page.addInitScript(() => localStorage.setItem('language', 'ru'));
  await page.route('**/api/v1/**', route => {
    const request = route.request(), path = new URL(request.url()).pathname;
    requests.push(path);
    let json = {};
    if (path.endsWith('/auth/session') || path.endsWith('/users/me')) {
      if (anonymous) return route.fulfill({ status: 401, json: { detail: 'Not authenticated' } });
      json = user;
    } else if (path === '/api/v1/campaign/cycles/current') {
      if (navigationError) return route.fulfill({ status: 503, json: {} });
      json = { mechanics_version: mode, cycle: noCycle ? null : { id: 7 }, territory_battles: [] };
    } else if (path === '/api/v1/campaign/cycles/7') json = { id: 7, season_id: 1 };
    else if (path === '/api/v1/clans/my') json = foreign ? { id: 12, name: 'Other clan', leader_id: 1 } : clan;
    else if (path === '/api/v1/clans/11') json = clan;
    else if (path === '/api/v1/clans/11/members') json = [
      { id: 3, user_id: clan.leader_id, username: 'Head', rank: 'Глава клана' },
      ...(member ? [{ id: 4, user_id: 1, username: 'Member', rank: 'Салага' }] : []),
    ];
    else if (path === '/api/v1/clans/') json = [clan, { id: 12, name: 'Other clan' }];
    else if (path === '/api/v1/clans/market/offers') json = { offers: [], clan_activity: [], caravans: [] };
    else if (path.includes('/economy/seasons/')) {
      if (request.method() === 'GET') json = data;
      else {
        const body = request.postDataJSON();
        writes.push({ path, ...body });
        data.state.revision += 1;
        if (path.endsWith('/active-relics')) data.state.active_relics = body.selected;
        json = data.state;
      }
    } else if (path.endsWith('/market/cycles/7')) json = { offers: [] };
    else if (path.endsWith('/market/cycles/7/clans/11')) json = { offers: [], caravans: [] };
    else if (path.includes('notifications')) json = { items: [], unread_count: 0, total: 0 };
    else if (path.includes('presence')) json = { items: [] };
    else if (path.endsWith('/stats')) json = { total_matches: 0, wins: 0, losses: 0, win_rate: 0, elo_ratings: {} };
    else if (path.endsWith('/users/2')) json = { id: 2, username: 'Other head' };
    else json = [];
    return route.fulfill({ json });
  });
  return { requests, writes };
}

const noLegacyRequests = requests => expect(requests.filter(path =>
  /\/clans\/11\/(assets|economy)$/.test(path) || path === '/api/v1/clans/market/offers')).toEqual([]);
const openTab = async (page, name) => {
  await page.locator('.clan-section-tabs').getByRole('tab', { name: ['Рынок', 'Обмен'].includes(name) ? 'Торговля' : name, exact: true }).click();
  if (['Рынок', 'Обмен'].includes(name)) await page.getByRole('group', { name: 'Режим торговли' }).getByRole('button', { name: name === 'Обмен' ? 'Межклановый обмен' : 'Рынок за золото', exact: true }).click();
};

for (const [key, label, content] of [
  ['development', 'Развитие', '.ce-land'],
  ['barter', 'Торговля', '.cycle-barter'],
]) {
  test(`canonical clan link opens ${key} and tab navigation preserves readable keys`, async ({ page }) => {
    await mockClan(page);
    await page.goto(`/clans/11?tab=${key}`);
    await expect(page.locator('.clan-section-tabs').getByRole('tab', { name: label, exact: true })).toHaveAttribute('aria-selected', 'true');
    await expect(page.locator(content)).toBeVisible();
    await openTab(page, 'Рынок');
    await expect(page).toHaveURL(/\/clans\/11\?tab=market$/);
    await page.goBack();
    await expect(page).toHaveURL(new RegExp(`tab=${key}$`));
    await expect(page.locator(content)).toBeVisible();
    await page.reload();
    await expect(page.locator(content)).toBeVisible();
  });
}

test('cycle clan header has no separate treasury or battles buttons', async ({ page }) => {
  await mockClan(page);
  await page.goto('/clans/11');
  await expect(page.locator('.clan-section-tabs')).toBeVisible();
  await expect(page.locator('.clan-view-page').getByRole('link', { name: /^(Казна и развитие|Битвы цикла)$/ })).toHaveCount(0);
  await expect(page.locator('.clan-view-page').getByRole('button', { name: /^(Казна и развитие|Битвы цикла)$/ })).toHaveCount(0);
});

test('legacy market and barter links share one native trade tab and preserve their modes', async ({ page }) => {
  await mockClan(page);
  for (const [key, mode] of [['market', 'Рынок за золото'], ['barter', 'Межклановый обмен']]) {
    await page.goto(`/clans/11?tab=${key}`);
    const tabs = page.locator('.clan-section-tabs');
    await expect(tabs.getByRole('tab', { name: 'Торговля', exact: true })).toHaveAttribute('aria-selected', 'true');
    await expect(tabs.getByRole('tab', { name: /^(Рынок|Обмен)$/ })).toHaveCount(0);
    await expect(page.getByRole('group', { name: 'Режим торговли' }).getByRole('button', { name: mode, exact: true })).toHaveAttribute('aria-pressed', 'true');
  }
});

test('development rows show current and next effects without oversized branch blocks', async ({ page }) => {
  const data = economy();
  data.lands[0].quotes.gold = { level: 2, next_effect: '265', cost: price };
  data.lands[0].quotes.naval = { level: 0, next_effect: '5', cost: null };
  data.lands[0].quotes.offense = { level: 3, next_effect: null, cost: null };
  await mockClan(page, { data });
  await page.goto('/clans/11?tab=development');
  const rows = page.locator('.ce-upgrade-row');
  await expect(rows).toHaveCount(3);
  await expect(rows.first()).toContainText('115');
  await expect(rows.first()).toContainText('265');
  await expect(rows.nth(1)).toContainText('Недоступно на этой земле');
  await expect(rows.nth(2)).toContainText('Максимальный уровень');
  await expect(rows.nth(1).getByRole('button')).toBeDisabled();
  expect((await rows.first().boundingBox()).height).toBeLessThan(100);
  expect((await page.locator('.clan-header').boundingBox()).height).toBeLessThan(240);
  await page.screenshot({ path: 'test-results/cycle-development-1440.png', fullPage: true });
});

test('starter gifts are explicitly separate from activation and require exactly two choices', async ({ page }) => {
  const data = economy();
  data.state.starters_chosen = false;
  data.state.relics = {};
  data.catalog.push({ ...data.catalog[0], key: 'dwarf_anvil', name: 'Наковальня Глубин' });
  const { writes } = await mockClan(page, { data });
  await page.goto('/clans/11?tab=relics');
  await expect(page.locator('.ce-starter-help')).toContainText('не активирует');
  await expect(page.getByRole('checkbox', { name: 'Активная реликвия', exact: true })).toHaveCount(0);
  const gifts = page.getByRole('checkbox', { name: /В подарок/ });
  await gifts.first().check();
  await expect(page.getByRole('button', { name: 'Получить выбранные реликвии' })).toBeDisabled();
  await gifts.nth(1).check();
  await page.getByRole('button', { name: 'Получить выбранные реликвии' }).click();
  await expect.poll(() => writes.length).toBe(1);
  expect(writes[0]).toMatchObject({ selected: ['white_tree', 'dwarf_anvil'], expected_revision: 1 });
});

test('development expands only the chosen territory and collapses with the keyboard', async ({ page }) => {
  const data = economy();
  const quotes = { gold: { level: 2, next_effect: '265', cost: price }, profile: { level: 1, next_effect: '5', cost: price }, mithril: { level: 0, next_effect: '0.5', cost: null }, fortification: { level: 1, next_effect: '10', cost: price }, offense: { level: 3, next_effect: null, cost: null }, naval: { level: 0, next_effect: '5', cost: null } };
  data.lands = ['Минас Тирит', 'Пеларгир', 'Осгилиат'].map((name, index) => ({ territory_id: 10 + index, name, revision: 0, quotes }));
  await mockClan(page, { data });
  await page.goto('/clans/11?tab=development');
  const lands = page.locator('details.ce-land');
  await expect(lands).toHaveCount(3);
  await expect(lands.first()).toHaveAttribute('open', '');
  await expect(lands.first().locator('summary')).toContainText('115');
  await lands.nth(1).locator('summary').click();
  await expect(lands.first()).not.toHaveAttribute('open', '');
  await expect(lands.nth(1).locator('.ce-upgrade-row').first()).toBeVisible();
  await expect(lands.nth(1)).toContainText('265');
  await expect(lands.nth(1)).toContainText('3000');
  await lands.nth(1).locator('summary').focus();
  await page.keyboard.press('Enter');
  await expect(lands.nth(1)).not.toHaveAttribute('open', '');
  await page.keyboard.press('Space');
  await expect(lands.nth(1).locator('.ce-upgrade-row').first()).toBeVisible();
  expect((await page.locator('.clan-cycle-economy').boundingBox()).height).toBeLessThan(750);
  await page.screenshot({ path: 'test-results/cycle-development-1440.png', fullPage: true });
});

for (const width of [1440, 390]) {
  test(`own cycle economy uses the clan tabs without nested navigation at ${width}px`, async ({ page }) => {
    const { requests } = await mockClan(page);
    await page.setViewportSize({ width, height: 1000 });
    await page.goto('/clans/11');
    const tabs = page.locator('.clan-section-tabs');
    await expect(tabs.getByRole('tab')).toHaveText(['Обзор', 'Игроки', 'Территории', 'Реликвии', 'Развитие', 'Торговля', 'История']);
    await openTab(page, 'Реликвии');
    const content = page.locator('.cycle-economy');
    await expect(content.locator('.ce-relic')).toContainText('Знамя Белого Древа');
    await expect(content.getByRole('heading', { name: /Казна и развитие|Own clan/ })).toHaveCount(0);
    await expect(content.getByRole('link', { name: 'Битвы цикла' })).toHaveCount(0);
    await expect(content.getByRole('tablist')).toHaveCount(0);
    await expect(page.locator('.clan-view-page').getByRole('tablist')).toHaveCount(1);
    await expect(content.getByRole('tabpanel')).toHaveAccessibleName('Реликвии');
    await expect.poll(() => content.locator('.ce-relic img').evaluate(img => img.complete && img.naturalWidth > 0)).toBe(true);
    await page.getByRole('checkbox', { name: 'Активная реликвия', exact: true }).check();
    await openTab(page, 'Обзор');
    await openTab(page, 'Игроки');
    await openTab(page, 'Реликвии');
    await expect(page.getByRole('checkbox', { name: 'Активная реликвия', exact: true })).toBeChecked();
    await openTab(page, 'Развитие');
    await expect(content.locator('.ce-land')).toContainText('Home');
    await openTab(page, 'Рынок');
    await expect(content.getByRole('textbox', { name: 'Количество', exact: true })).toBeVisible();
    await openTab(page, 'Обмен');
    await expect(content.getByRole('button', { name: 'Выставить обмен', exact: true })).toBeVisible();
    await openTab(page, 'Реликвии');
    await expect(page.getByRole('checkbox', { name: 'Активная реликвия', exact: true })).toBeChecked();
    noLegacyRequests(requests);
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    await page.screenshot({ path: `test-results/cycle-clan-economy-${width}.png`, fullPage: true, animations: 'disabled' });
  });
}

test('embedded upgrades and market keep confirmation and revision payloads', async ({ page }) => {
  const { writes } = await mockClan(page);
  await page.goto('/clans/11#relics');
  await expect(page.locator('.ce-relic')).toBeVisible();
  await openTab(page, 'Развитие');
  await page.getByRole('button', { name: 'Улучшить', exact: true }).click();
  await expect(page.getByRole('dialog')).toContainText('300');
  expect(writes).toHaveLength(0);
  await page.getByRole('dialog').getByRole('button', { name: 'Подтвердить', exact: true }).click();
  await expect.poll(() => writes.length).toBe(1);
  expect(writes[0]).toMatchObject({ territory_id: 10, branch: 'gold', expected_upgrade_revision: 0, expected_revision: 1 });
  await expect(page.getByRole('status')).toContainText('Изменения сохранены');
  await openTab(page, 'Рынок');
  await page.getByRole('textbox', { name: 'Количество', exact: true }).fill('2');
  await page.getByRole('button', { name: 'Подтвердить обмен с рынком' }).click();
  expect(writes).toHaveLength(1);
  await page.getByRole('dialog').getByRole('button', { name: 'Подтвердить', exact: true }).click();
  await expect.poll(() => writes.length).toBe(2);
  expect(writes[1]).toMatchObject({ resource: 'iron', quantity: '2', buying: true, expected_revision: 2 });
});

test('embedded barter retries preserve the UUID across clan tabs', async ({ page }) => {
  await mockClan(page);
  const writes = [];
  await page.route('**/market/cycles/7/clans/11/offers', route => {
    writes.push(route.request().postDataJSON());
    return route.fulfill({ status: writes.length === 1 ? 503 : 200, json: { id: 9 } });
  });
  await page.goto('/clans/11');
  await openTab(page, 'Обмен');
  for (let attempt = 0; attempt < 2; attempt++) {
    await page.getByRole('button', { name: 'Выставить обмен', exact: true }).click();
    await page.getByRole('combobox', { name: 'Отдать: ресурс 1', exact: true }).selectOption('wood');
    await page.getByRole('combobox', { name: 'Получить: ресурс 1', exact: true }).selectOption('mithril');
    await page.getByRole('textbox', { name: 'Отдать: Дерево', exact: true }).fill('10');
    await page.getByRole('textbox', { name: 'Получить: Мифрил', exact: true }).fill('1');
    await page.getByRole('button', { name: 'Проверить предложение', exact: true }).click();
    await expect(page.getByRole('dialog')).toContainText('Комиссия золотом: 30');
    expect(writes).toHaveLength(attempt);
    await page.getByRole('dialog').getByRole('button', { name: 'Подтвердить', exact: true }).click();
    if (!attempt) {
      await expect(page.getByRole('alert')).toBeVisible();
      await openTab(page, 'Обзор');
      await openTab(page, 'Обмен');
    }
  }
  await expect.poll(() => writes.length).toBe(2);
  expect(writes[0]).toMatchObject({ expected_wallet_revision: 1, offered: { wood: '10' }, requested: { mithril: '1' } });
  expect(writes[0].command_id).toMatch(/^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i);
  expect(writes[1].command_id).toBe(writes[0].command_id);
});

test('read-only cycle members do not gain economy commands', async ({ page }) => {
  const data = economy();
  data.can_manage = false; data.can_select = false; data.can_trade = false;
  const { writes } = await mockClan(page, { data, member: true });
  await page.goto('/clans/11#relics');
  await expect(page.locator('.ce-relic')).toBeVisible();
  await expect(page.getByRole('button', { name: 'Улучшить', exact: true })).toHaveCount(0);
  await expect(page.getByRole('checkbox', { name: 'Активная реликвия', exact: true })).toBeDisabled();
  await openTab(page, 'Рынок');
  await expect(page.getByRole('textbox', { name: 'Количество', exact: true })).toBeDisabled();
  await expect(page.getByRole('button', { name: 'Подтвердить обмен с рынком' })).toHaveCount(0);
  await openTab(page, 'Обмен');
  await expect(page.getByRole('button', { name: 'Выставить обмен', exact: true })).toHaveCount(0);
  expect(writes).toHaveLength(0);
});

for (const options of [{ foreign: true }, { noCycle: true }, { navigationError: true }]) {
  test(`public clan stays private and never falls back to legacy: ${JSON.stringify(options)}`, async ({ page }) => {
    const { requests } = await mockClan(page, options);
    await page.goto('/clans/11?tab=barter');
    await expect(page.locator('.clan-section-tabs').getByRole('tab', { name: 'Обзор', exact: true })).toHaveAttribute('aria-selected', 'true');
    await expect(page.locator('.clan-section-tabs').getByRole('tab')).toHaveText(['Обзор', 'Игроки', 'Территории', 'История']);
    await openTab(page, 'Игроки');
    await expect(page.locator('.clan-player-table')).toBeVisible();
    await openTab(page, 'Территории');
    await expect(page.locator('.clan-territories-panel')).toBeVisible();
    await expect(page.locator('.cycle-economy')).toHaveCount(0);
    expect(requests.filter(path => path.includes('/economy/seasons/') || path.includes('/market/cycles/'))).toEqual([]);
    noLegacyRequests(requests);
  });
}

test('anonymous access keeps the existing sign-in guard without private requests', async ({ page }) => {
  const { requests } = await mockClan(page, { anonymous: true });
  await page.goto('/clans/11#relics');
  await expect(page.getByRole('dialog', { name: /Войдите, чтобы продолжить/ })).toBeVisible();
  await expect(page.locator('.cycle-economy')).toHaveCount(0);
  expect(requests.filter(path => path.includes('/economy/seasons/') || path.includes('/market/cycles/'))).toEqual([]);
});

test('legacy clans keep their existing public tabs and economy', async ({ page }) => {
  const { requests } = await mockClan(page, { mode: 'legacy', foreign: true });
  await page.goto('/clans/11');
  await expect(page.locator('.clan-section-tabs').getByRole('tab')).toHaveText(['Обзор', 'Игроки', 'Территории', 'Торговля', 'Реликвии клана', 'Битвы', 'История']);
  await openTab(page, 'Реликвии клана');
  await expect(page.locator('.clan-relics-prototype')).toBeVisible();
  expect(requests).toContain('/api/v1/clans/11/assets');
  expect(requests.filter(path => path.includes('/economy/seasons/'))).toEqual([]);
});
