import { test, expect } from '@playwright/test';

async function market(page, { canTrade = true } = {}) {
  const offers = [
    { id: 4, sender_clan_id: 12, status: 'pending', revision: 2, offered: { iron: '2.5' }, requested: { wood: '3' }, expires_after_cycle: 4 },
    { id: 5, sender_clan_id: 11, target_clan_id: 12, status: 'pending', revision: 1, offered: { food: '10' }, requested: { mithril: '1' }, expires_after_cycle: 4 },
    { id: 6, sender_clan_id: 11, accepter_clan_id: 12, status: 'accepted', revision: 2, offered: { food: '20' }, requested: { iron: '2' }, expires_after_cycle: 3 },
  ];
  const writes = [];
  await page.setViewportSize({ width: 1440, height: 1000 });
  await page.addInitScript(() => localStorage.setItem('language', 'ru'));
  await page.route('**/api/v1/**', route => {
    const req = route.request(), path = new URL(req.url()).pathname;
    let json = [];
    const clan = { id: 11, name: 'Белое Древо', leader_id: 1, member_count: 1, created_at: '2026-01-01T00:00:00Z' };
    if (path.endsWith('/auth/session') || path.endsWith('/users/me')) json = { id: 1, username: 'Head', language: 'ru', is_verified: true, is_claimed: true, onboarding_completed: true, role: { name: 'user' } };
    else if (path.endsWith('/campaign/cycles/current')) json = { mechanics_version: 'cycle_v1', cycle: { id: 7 }, territory_battles: [] };
    else if (path.endsWith('/campaign/cycles/7')) json = { id: 7, season_id: 1 };
    else if (path === '/api/v1/clans/my' || path === '/api/v1/clans/11') json = clan;
    else if (path.endsWith('/clans/11/members')) json = [{ id: 1, user_id: 1, username: 'Head', rank: 'Глава клана' }];
    else if (path.endsWith('/clans/')) json = [clan, { id: 12, name: 'Стражи Севера' }];
    else if (path.endsWith('/context')) json = { season_id: 1, cycle_id: 7, clan_id: 11, clan_name: clan.name, ready: true, can_manage: false, can_select: false, can_trade: canTrade,
      state: { revision: 1, wallet: { gold: '10000', iron: '100', wood: '200', food: '300', mithril: '10' }, relics: {}, active_relics: [], starters_chosen: true }, catalog: [],
      market_buy: { iron: '45', wood: '40', food: '30', mithril: '300' }, market_sell: { iron: '10', wood: '8', food: '6', mithril: '60' }, lands: [{ territory_id: 10, name: 'Home', quotes: {} }] };
    else if (path.endsWith('/offers/4/quote')) json = { expected_revision: 2, expected_sender_revision: 7, expected_wallet_revision: 1, fee_gold: '11.25', travel_hours: 18, arrives_at: '2026-10-28T12:00:00Z' };
    else if (req.method() === 'POST') { writes.push({ path, ...req.postDataJSON() }); json = {}; }
    else if (path.endsWith('/market/cycles/7')) json = { offers: [offers[0]] };
    else if (path.endsWith('/market/cycles/7/clans/11')) json = { offers: offers.slice(1), caravans: [{ id: 9, offer_id: 6, cargo: { iron: '2' }, route: { travel_hours: 12, travel_steps: 2 }, arrives_at: '2026-10-28T12:00:00Z' }] };
    else if (path.includes('notifications')) json = { items: [], total: 0, unread_count: 0 };
    else if (path.includes('presence')) json = { items: [] };
    return route.fulfill({ json });
  });
  return writes;
}

for (const width of [1440, 390]) test(`trade rows use viewer cargo direction and compact history at ${width}px`, async ({ page }) => {
  const writes = await market(page);
  await page.setViewportSize({ width, height: 1000 });
  await page.goto('/clans/11?tab=barter');
  const incoming = page.locator('.cb-offer').filter({ hasText: 'Стражи Севера' }).first();
  await expect(incoming.locator('.cb-give')).toContainText('3 Дерево');
  await expect(incoming.locator('.cb-receive')).toContainText('2.5 Железо');
  await expect(page.locator('.cb-offer').filter({ hasText: 'Белое Древо' }).first().locator('.cb-give')).toContainText('10 Еда');
  await expect(page.locator('.cb-offer').filter({ hasText: 'Ваше предложение' }).first()).toContainText('Стражи Севера');
  await expect(page.locator('.cycle-barter form')).toHaveCount(0);
  await page.getByRole('button', { name: 'Принять обмен', exact: true }).click();
  await expect(page.getByRole('dialog')).toContainText('11.25');
  await expect(page.getByRole('dialog')).toContainText('18');
  expect(writes).toHaveLength(0);
  await page.getByRole('dialog').getByRole('button', { name: 'Подтвердить', exact: true }).click();
  await expect.poll(() => writes.length).toBe(1);
  expect(writes[0]).toMatchObject({ expected_revision: 2, expected_sender_revision: 7, expected_wallet_revision: 1 });
  await expect(page.getByRole('dialog')).not.toBeVisible();
  await expect(page.locator('.cb-dialog')).toHaveCount(0);
  await expect(page.locator('.cb-history summary')).toContainText('История');
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await page.screenshot({ path: `test-results/cycle-trade-${width}.png`, fullPage: true, animations: 'disabled' });
});

test('offer dialog supports multiple materials without a gold cargo option and restores focus', async ({ page }) => {
  const writes = await market(page);
  await page.goto('/clans/11?tab=barter');
  const create = page.getByRole('button', { name: 'Выставить обмен', exact: true });
  await create.click();
  const dialog = page.getByRole('dialog');
  await expect(dialog.getByRole('textbox')).toHaveCount(2);
  await expect(dialog.getByRole('combobox', { name: 'Отдать: ресурс 1' }).locator('option', { hasText: 'Золото' })).toHaveCount(0);
  await dialog.getByRole('textbox', { name: 'Отдать: Дерево' }).fill('10');
  await dialog.getByRole('button', { name: 'Отдать: добавить ресурс' }).click();
  await dialog.getByRole('textbox', { name: 'Отдать: Железо' }).fill('2');
  await dialog.getByRole('textbox', { name: 'Получить: Мифрил' }).fill('1');
  await dialog.getByRole('button', { name: 'Проверить предложение' }).click();
  await expect(dialog).toContainText('Комиссия золотом: 30');
  await expect(dialog).toContainText('после выбора второго клана');
  await dialog.getByRole('button', { name: 'Подтвердить', exact: true }).click();
  await expect.poll(() => writes.length).toBe(1);
  expect(writes[0]).toMatchObject({ offered: { wood: '10', iron: '2' }, requested: { mithril: '1' }, expected_wallet_revision: 1 });
  await expect(create).toBeFocused();
});

test('market sale shows full give/get total and retains sell command', async ({ page }) => {
  const writes = await market(page);
  await page.goto('/clans/11?tab=market');
  await page.getByRole('combobox', { name: 'Операция' }).selectOption('sell');
  await page.getByRole('textbox', { name: 'Количество', exact: true }).fill('3');
  await expect(page.locator('.ce-market-summary')).toContainText('30 Золото');
  await page.getByRole('button', { name: 'Подтвердить обмен с рынком' }).click();
  await expect(page.getByRole('dialog')).toContainText('30 Золото');
  await page.getByRole('dialog').getByRole('button', { name: 'Подтвердить', exact: true }).click();
  await expect.poll(() => writes.length).toBe(1);
  expect(writes[0]).toMatchObject({ buying: false, resource: 'iron', quantity: '3', expected_revision: 1 });
});
