import { test, expect } from '@playwright/test';
const resource = { gold: '10000', iron: '1000', wood: '1000', food: '1000', mithril: '100' };
const price = { gold: '3000', iron: '15', wood: '25', food: '20', mithril: '4' };
const context = () => ({ season_id: 1, cycle_id: 1, clan_id: 7, clan_name: 'Akatsuki', phase: 'preparation', ready: true,
  can_manage: true, can_select: true, can_trade: true,
  state: { revision: 1, wallet: resource, relics: { white_tree: 1 }, active_relics: [], starters_chosen: true },
  catalog: [{ key: 'white_tree', name: 'Знамя Белого Древа', effect: 'gold', effects: ['15', '25', '35'], costs: [price, price, price] }],
  market_buy: { iron: '45', wood: '40', food: '30', mithril: '300' }, market_sell: { iron: '10', wood: '8', food: '6', mithril: '60' },
  lands: [{ territory_id: 10, name: 'Home', revision: 0, quotes: { gold: { level: 0, next_effect: '35', cost: { gold: '300', iron: '5', wood: '10', food: '5', mithril: '0' } } } }] });
async function mock(page, data) {
  const commands = [];
  const user = { id: 1, username: 'Head', language: 'ru', is_verified: true, is_claimed: true, role: { name: 'user' }, onboarding_completed: true };
  await page.addInitScript(() => localStorage.setItem('language', 'ru'));
  await page.route('**/api/v1/**', route => {
    const req = route.request(), path = new URL(req.url()).pathname;
    let payload = {};
    if (path.endsWith('/auth/session') || path.endsWith('/users/me')) payload = user;
    else if (path.endsWith('/clans/my')) payload = { id: 7, leader_id: 1 };
    else if (path === '/api/v1/campaign/cycles/1') payload = { id: 1, season_id: 1 };
    else if (path.endsWith('/context')) payload = data;
    else if (['POST', 'PUT'].includes(req.method()) && path.includes('/economy/')) {
      const body = req.postDataJSON(); commands.push({ path, ...body });
      data.state.revision += 1;
      if (path.endsWith('/active-relics')) data.state.active_relics = body.selected;
      payload = data.state;
    } else if (path.includes('notifications')) payload = { items: [], unread_count: 0, total: 0 };
    else if (path.includes('presence')) payload = { items: [] };
    else if (path.includes('localization')) payload = [];
    return route.fulfill({ json: payload });
  });
  return commands;
}
for (const width of [390, 1440]) {
  test(`relic levels, artwork and active selection at ${width}px`, async ({ page }) => {
    await page.setViewportSize({ width, height: 1000 });
    const writes = await mock(page, context());
    await page.goto('/campaign/cycles/1/economy');
    await expect(page.getByRole('heading', { name: 'Казна и развитие' })).toBeVisible();
    const relic = page.locator('.ce-relic');
    await expect(relic).toContainText('Знамя Белого Древа');
    await expect(relic.getByRole('table')).toContainText('35%');
    await expect.poll(() => relic.locator('img').evaluate(img => img.complete && img.naturalWidth > 0)).toBe(true);
    await page.getByRole('checkbox', { name: 'Активная реликвия', exact: true }).check();
    await page.getByRole('button', { name: 'Сохранить активный набор' }).click();
    await expect(page.getByRole('status')).toContainText('Изменения сохранены');
    expect(writes[0]).toMatchObject({ selected: ['white_tree'], cycle_id: 1, expected_revision: 1 });
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    await page.evaluate(() => window.scrollTo({ top: 0, behavior: 'instant' }));
    await page.screenshot({ path: `test-results/cycle-economy-${width}.png`, fullPage: true });
  });
}
test('territory upgrade uses both revisions and purchase confirmation', async ({ page }) => {
  const writes = await mock(page, context());
  await page.goto('/campaign/cycles/1/economy');
  await page.getByRole('tab', { name: 'Территории', exact: true }).click();
  await page.getByRole('button', { name: 'Улучшить', exact: true }).click();
  await expect(page.getByRole('dialog')).toContainText('300');
  await page.getByRole('dialog').getByRole('button', { name: 'Подтвердить', exact: true }).click();
  await expect.poll(() => writes.length).toBe(1);
  expect(writes[0]).toMatchObject({ territory_id: 10, branch: 'gold', expected_upgrade_revision: 0, expected_revision: 1 });
});
test('appointed trader may use market but cannot manage relics', async ({ page }) => {
  const data = context(); data.can_manage = false; data.can_select = false;
  const writes = await mock(page, data);
  await page.goto('/campaign/cycles/1/economy');
  await expect(page.getByRole('button', { name: 'Улучшить', exact: true })).toHaveCount(0);
  await page.getByRole('tab', { name: 'Торговля', exact: true }).click();
  await page.getByRole('textbox', { name: 'Количество', exact: true }).fill('2');
  await page.getByRole('button', { name: 'Подтвердить обмен с рынком' }).click();
  await page.getByRole('dialog').getByRole('button', { name: 'Подтвердить', exact: true }).click();
  await expect.poll(() => writes.length).toBe(1);
  expect(writes[0]).toMatchObject({ resource: 'iron', quantity: '2', buying: true });
});

test('unrelated purchase cannot discard an unsaved active loadout', async ({ page }) => {
  await mock(page, context());
  await page.goto('/campaign/cycles/1/economy');
  await page.getByRole('checkbox', { name: 'Активная реликвия', exact: true }).check();
  await page.getByRole('button', { name: 'Улучшить', exact: true }).click();
  await page.getByRole('dialog').getByRole('button', { name: 'Подтвердить', exact: true }).click();
  await expect(page.getByRole('status')).toContainText('Изменения сохранены');
  await expect(page.getByRole('checkbox', { name: 'Активная реликвия', exact: true })).toBeChecked();
  await expect(page.getByRole('button', { name: 'Сохранить активный набор' })).toBeEnabled();
});

test('barter accepts only material cargo and uses the quoted revisions and fee', async ({ page }) => {
  await mock(page, context());
  const offer = { id: 4, sender_clan_id: 8, target_clan_id: null, status: 'pending', revision: 2, expires_after_cycle: 3,
    offered: { iron: '2.5' }, requested: { wood: '3' } };
  await page.route('**/api/v1/clans/', route => route.fulfill({ json: [{ id: 7, name: 'Akatsuki' }, { id: 8, name: 'Other' }] }));
  await page.route('**/market/cycles/1', route => route.fulfill({ json: { offers: [offer] } }));
  await page.route('**/market/cycles/1/clans/7', route => route.fulfill({ json: { offers: [], caravans: [] } }));
  await page.route('**/offers/4/quote', route => route.fulfill({ json: { expected_revision: 2, expected_sender_revision: 7,
    expected_wallet_revision: 1, fee_gold: '11.25', arrives_at: '2026-10-20T00:00:00Z' } }));
  const writes = [];
  await page.route('**/offers/4/accept', route => { writes.push(route.request().postDataJSON()); return route.fulfill({ json: { ...offer, status: 'accepted' } }); });
  await page.goto('/campaign/cycles/1/economy');
  await page.getByRole('tab', { name: 'Торговля', exact: true }).click();
  await page.getByRole('button', { name: 'Межклановый обмен', exact: true }).click();
  await page.getByRole('button', { name: 'Принять обмен', exact: true }).click();
  await expect(page.getByRole('dialog')).toContainText('11.25');
  await expect(page.getByRole('textbox', { name: 'Отдать: Золото' })).toHaveCount(0);
  await page.getByRole('dialog').getByRole('button', { name: 'Подтвердить', exact: true }).click();
  await expect.poll(() => writes.length).toBe(1);
  expect(writes[0]).toMatchObject({ expected_revision: 2, expected_sender_revision: 7, expected_wallet_revision: 1 });
  expect(writes[0].command_id).toBeTruthy();
});

test('uncertain barter creation keeps its command after treasury refresh and previews creator fee', async ({ page }) => {
  await mock(page, context());
  await page.route('**/api/v1/clans/', route => route.fulfill({ json: [] }));
  await page.route('**/market/cycles/1', route => route.fulfill({ json: { offers: [] } }));
  await page.route('**/market/cycles/1/clans/7', route => route.fulfill({ json: { offers: [], caravans: [] } }));
  const writes = [];
  await page.route('**/market/cycles/1/clans/7/offers', route => {
    writes.push(route.request().postDataJSON());
    return route.fulfill({ status: writes.length === 1 ? 503 : 200, json: { id: 9 } });
  });
  await page.goto('/campaign/cycles/1/economy');
  await page.getByRole('tab', { name: 'Торговля', exact: true }).click();
  await page.getByRole('button', { name: 'Межклановый обмен', exact: true }).click();
  for (let attempt = 0; attempt < 2; attempt++) {
    await page.getByRole('button', { name: 'Выставить обмен', exact: true }).click();
    await page.getByRole('combobox', { name: 'Отдать: ресурс 1', exact: true }).selectOption('wood');
    await page.getByRole('combobox', { name: 'Получить: ресурс 1', exact: true }).selectOption('mithril');
    await page.getByRole('textbox', { name: 'Отдать: Дерево', exact: true }).fill('10');
    await page.getByRole('textbox', { name: 'Получить: Мифрил', exact: true }).fill('1');
    await page.getByRole('button', { name: 'Проверить предложение', exact: true }).click();
    await expect(page.getByRole('dialog')).toContainText('Комиссия золотом: 30');
    await page.getByRole('dialog').getByRole('button', { name: 'Подтвердить', exact: true }).click();
    if (!attempt) {
      await expect(page.getByRole('alert')).toBeVisible();
      await page.locator('.cycle-economy header button').click();
    }
  }
  await expect.poll(() => writes.length).toBe(2);
  expect(writes[0].command_id).toBe(writes[1].command_id);
});

test('cancel confirmation describes the actual reserved refund', async ({ page }) => {
  await mock(page, context());
  const offer = { id: 5, sender_clan_id: 7, target_clan_id: null, status: 'pending', revision: 1, expires_after_cycle: 3,
    offered: { wood: '10' }, requested: { mithril: '1' } };
  await page.route('**/api/v1/clans/', route => route.fulfill({ json: [] }));
  await page.route('**/market/cycles/1', route => route.fulfill({ json: { offers: [] } }));
  await page.route('**/market/cycles/1/clans/7', route => route.fulfill({ json: { offers: [offer], caravans: [] } }));
  await page.goto('/campaign/cycles/1/economy');
  await page.getByRole('tab', { name: 'Торговля', exact: true }).click();
  await page.getByRole('button', { name: 'Межклановый обмен', exact: true }).click();
  await page.getByRole('button', { name: 'Отменить предложение', exact: true }).click();
  await expect(page.getByRole('dialog')).toContainText('Возврат резерва: 10 Дерево');
});
