import { test, expect } from '@playwright/test';

async function setup(page, { reason = 'no_adjacent_land_or_port', context = {}, contextStatus = 200, editable = true } = {}) {
  const writes = [];
  const lands = [
    { id: 3, name: 'Арнор', owner_clan_id: 8, is_playable: true, adjacent_territory_ids: [] },
    { id: 4, name: 'Форност', owner_clan_id: 7, is_playable: true, adjacent_territory_ids: [5] },
    { id: 5, name: 'Гондор', owner_clan_id: 8, is_playable: true, adjacent_territory_ids: [4] },
  ];
  const now = new Date().toISOString();
  const planning = {
    cycle_id: 1, clan_id: 7, phase: 'preparation', editable, snapshot_ready: reason !== 'snapshot_missing',
    server_time: now, battle_at: new Date(Date.now() + 86400000).toISOString(),
    plan: { revision: 2, orders: [{ user_id: 2, kind: 'reserve', territory_id: null, source_id: null, route: 'land' }] },
    members: [{ user_id: 1, name: 'Воин', eligible: true }, { user_id: 2, name: 'Резервист', eligible: true }],
    limits: { attacks: 2, reserves: 2, ambush_players: 2 }, territories: lands, defence_targets: [4],
    attack_routes: reason === 'snapshot_missing' ? [] : [{ territory_id: 5, source_id: 4, route: 'land' }],
    attack_unavailable: [{ territory_id: 3, reason }],
  };
  const reinforcement = {
    cycle_id: 1, clan_id: 7, clan_name: 'Демо', phase: 'battle', ready: true, can_command: true,
    server_time: now, command_deadline: new Date(Date.now() + 86400000).toISOString(),
    players: [{ user_id: 2, name: 'Резервист', available: true }], names: [{ user_id: 2, name: 'Резервист' }],
    own_targets: [{ territory_id: 3, battle_id: 50 }], help_targets: [3], allied_targets: [],
    origins: [{ territory_id: 4, name: 'Форност' }], route_previews: [], territories: lands,
    clans: [{ id: 7, name: 'Демо' }], state: { revision: 3, reserves: [], requests: [], dispatches: [], ambushes: [] },
    ...context,
  };
  await page.addInitScript(() => localStorage.setItem('language', 'ru'));
  await page.route('**/api/**', route => {
    const path = new URL(route.request().url()).pathname;
    let json = {};
    if (path.endsWith('/auth/session') || path.endsWith('/users/me')) json = { id: 1, username: 'Глава', language: 'ru', is_claimed: true, is_verified: true, onboarding_completed: true, role: { name: 'admin' } };
    else if (path.endsWith('/clans/my')) json = { id: 7, leader_id: 1, name: 'Демо' };
    else if (path.endsWith('/cycles/current')) json = { mechanics_version: 'cycle_v1', cycle: { id: 1 }, territory_battles: [] };
    else if (path.endsWith('/cycles/1/map')) json = { cycle_id: 1, clan_id: 7, phase: 'battle', ready: true, can_command: true, server_time: now, battles: [], dispatches: [], ambushes: [], requests: [], help_targets: [3], allied_targets: [], territories: [] };
    else if (path === '/api/v1/territories/') json = lands;
    else if (path === '/api/v1/clans/') json = [{ id: 7, name: 'Демо' }, { id: 8, name: 'Соседи' }];
    else if (path.endsWith('/planning')) json = planning;
    else if (path.endsWith('/reinforcements/context')) return route.fulfill({ status: contextStatus, json: reinforcement });
    else if (path.endsWith('/plan')) {
      const body = route.request().postDataJSON(); writes.push(body);
      planning.plan = { revision: 3, orders: body.orders }; json = planning.plan;
    } else if (path.includes('notifications')) json = { items: [], unread_count: 0 };
    else if (path.includes('presence')) json = { items: [] };
    else if (path.includes('localization') || path.includes('diplomacy') || path.endsWith('/wars/active/')) json = [];
    return route.fulfill({ json });
  });
  await page.setViewportSize({ width: 1440, height: 1000 });
  await page.goto('/map');
  await page.getByRole('button', { name: 'Арнор', exact: true }).press('Enter');
  await expect(page.locator('.cycle-map-panel')).toBeVisible();
  return { writes, reinforcement };
}

for (const [reason, explanation] of [
  ['owned', 'свою территорию'], ['ally', 'территорию союзника'],
  ['no_eligible_players', 'нет доступных игроков'],
  ['fortress_requirements', '5 земель и 350 влияния'],
  ['landless_port', 'Клан без земель не может атаковать порт'],
  ['no_adjacent_land_or_port', 'Нет соседней своей земли или подходящего морского маршрута'],
  ['snapshot_missing', 'Снимок подготовки ещё не готов'],
]) {
  test(`attack unavailability explains server reason ${reason}`, async ({ page }) => {
    const { writes } = await setup(page, { reason });
    await page.getByRole('button', { name: 'Распределить отряд', exact: true }).click();
    const dialog = page.getByRole('dialog').first();
    await expect(dialog).toContainText(explanation);
    await expect(dialog.getByRole('button', { name: 'Проверить приказ' })).toHaveCount(0);
    expect(writes).toEqual([]);
  });
}

test('only server-approved attack destinations can be chosen explicitly without changing selected map land', async ({ page }) => {
  const { writes } = await setup(page);
  await page.getByRole('button', { name: 'Распределить отряд', exact: true }).click();
  const dialog = page.getByRole('dialog').first();
  const targets = dialog.getByRole('combobox', { name: 'Цель атаки', exact: true });
  await expect(targets).toHaveValue('');
  await expect(targets.locator('option')).toHaveText(['Выберите доступную цель', 'Гондор']);
  await targets.selectOption('5');
  await dialog.getByRole('checkbox', { name: 'Воин', exact: true }).check();
  await dialog.getByRole('button', { name: 'Проверить приказ', exact: true }).click();
  const confirmation = page.getByRole('dialog', { name: 'Подтвердить приказ', exact: true });
  await expect(confirmation).toContainText('Гондор');
  await expect(confirmation).not.toContainText('Арнор');
  expect(writes).toEqual([]);
  await confirmation.getByRole('button', { name: 'Подтвердить', exact: true }).click();
  await expect.poll(() => writes.length).toBe(1);
  expect(writes[0]).toEqual({ expected_revision: 2, orders: [
    { user_id: 2, kind: 'reserve', territory_id: null, source_id: null, route: 'land' },
    { user_id: 1, kind: 'attack', territory_id: 5, source_id: 4, route: 'land' },
  ] });
  await dialog.getByRole('button', { name: 'Закрыть', exact: true }).click();
  await expect(page.getByRole('heading', { name: 'Арнор', exact: true }).first()).toBeVisible();
});

test('read-only planning explains phase and command permissions and cannot assign players', async ({ page }) => {
  const { writes } = await setup(page, { editable: false });
  await page.getByRole('button', { name: 'Распределить отряд', exact: true }).click();
  const dialog = page.getByRole('dialog').first();
  await expect(dialog).toContainText('Сейчас план доступен только для просмотра');
  await expect(dialog).toContainText('План изменяют глава и воевода во время подготовки');
  await expect(dialog.getByRole('combobox', { name: 'Цель атаки', exact: true })).toBeDisabled();
  expect(writes).toEqual([]);
});

for (const [name, context, contextStatus = 200] of [
  ['unrelated territory despite help targets', { own_targets: [], allied_targets: [] }],
  ['not revealed', { ready: false }], ['not authorized', { can_command: false }],
  ['preparation', { phase: 'preparation' }], ['no available reserves', { players: [{ user_id: 2, name: 'Резервист', available: false }] }],
  ['expired deadline', { command_deadline: '2020-01-01T00:00:00Z' }],
  ['wrong cycle', { cycle_id: 2 }], ['wrong clan', { clan_id: 8 }],
  ['unauthorized context', {}, 403],
]) {
  test(`reinforcement dispatch is hidden for ${name}`, async ({ page }) => {
    const response = page.waitForResponse('**/reinforcements/context').catch(() => null);
    await setup(page, { context, contextStatus });
    await expect(page.getByRole('button', { name: 'Отправить подкрепление', exact: true })).toHaveCount(0);
    await response;
    await expect(page.getByRole('button', { name: 'Отправить подкрепление', exact: true })).toHaveCount(0);
  });
}

test('authorized own battle with reserves exposes enabled reinforcement entry and dispatches selected target', async ({ page }) => {
  await setup(page, { context: { help_targets: [] } });
  const send = page.getByRole('button', { name: 'Отправить подкрепление', exact: true });
  await expect(send).toBeEnabled();
  await send.click();
  const dialog = page.getByRole('dialog').first();
  await expect(dialog.getByRole('combobox', { name: 'Куда отправить', exact: true })).toHaveValue('7:3:');
});

test('authorized allied request is selected instead of an invented own target', async ({ page }) => {
  await setup(page, { context: { own_targets: [], help_targets: [], allied_targets: [{ territory_id: 3, recipient_clan_id: 8, request_id: 'help-8' }] } });
  await page.getByRole('button', { name: 'Отправить подкрепление', exact: true }).click();
  await expect(page.getByRole('dialog').first().getByRole('combobox', { name: 'Куда отправить', exact: true })).toHaveValue('8:3:help-8');
});

test('reinforcement entry disappears at the server deadline without reopening the territory', async ({ page }) => {
  await page.clock.install();
  await setup(page, { context: { command_deadline: new Date(Date.now() + 5000).toISOString() } });
  const send = page.getByRole('button', { name: 'Отправить подкрепление', exact: true });
  await expect(send).toBeEnabled();
  await page.clock.fastForward(6000);
  await expect(send).toHaveCount(0);
});

test('a failed context refresh removes a previously authorized reinforcement entry', async ({ page }) => {
  await page.clock.install();
  await setup(page);
  const send = page.getByRole('button', { name: 'Отправить подкрепление', exact: true });
  await expect(send).toBeEnabled();
  await page.route('**/reinforcements/context', route => route.fulfill({ status: 403, json: { detail: 'Forbidden' } }));
  const response = page.waitForResponse('**/reinforcements/context');
  await page.clock.fastForward(15001);
  await response;
  await expect(send).toHaveCount(0);
});

test('late reinforcement response for another selected territory cannot expose its dispatch button', async ({ page }) => {
  let release;
  const gate = new Promise(resolve => { release = resolve; });
  await setup(page, { context: { own_targets: [] } });
  await page.route('**/reinforcements/context', async route => {
    await gate;
    return route.fulfill({ json: { cycle_id: 1, clan_id: 7, ready: true, can_command: true, phase: 'battle',
      server_time: new Date().toISOString(), command_deadline: new Date(Date.now() + 86400000).toISOString(),
      players: [{ user_id: 2, available: true }], own_targets: [{ territory_id: 3 }], allied_targets: [] } });
  });
  await page.getByRole('button', { name: 'Форност', exact: true }).press('Enter');
  await page.getByRole('button', { name: 'Арнор', exact: true }).press('Enter');
  const response = page.waitForResponse('**/reinforcements/context');
  await page.getByRole('button', { name: 'Форност', exact: true }).press('Enter');
  release();
  await response;
  await expect(page.getByRole('button', { name: 'Отправить подкрепление', exact: true })).toHaveCount(0);
});

for (const [name, width, height] of [['desktop', 1440, 1000], ['mobile', 390, 844]]) {
  test(`attack availability and approved destinations fit ${name}`, async ({ page }) => {
    await setup(page);
    await page.setViewportSize({ width, height });
    await page.getByRole('button', { name: 'Распределить отряд', exact: true }).click();
    const dialog = page.getByRole('dialog').first();
    await expect(dialog).toContainText('Нет соседней своей земли');
    const select = dialog.getByRole('combobox', { name: 'Цель атаки', exact: true });
    await expect(select).toBeEnabled();
    await select.selectOption('5');
    const bounds = await dialog.boundingBox();
    expect(bounds.x).toBeGreaterThanOrEqual(0);
    expect(bounds.x + bounds.width).toBeLessThanOrEqual(width);
    if (name === 'mobile') {
      const players = dialog.locator('fieldset li');
      const first = await players.nth(0).boundingBox(), second = await players.nth(1).boundingBox();
      expect(second.y).toBeGreaterThan(first.y);
    }
    await page.screenshot({ path: `../.tmp/map-availability-${name}.png`, fullPage: true });
  });
}
