import { test, expect } from '@playwright/test';

async function setup(page, { scoutAvailable = true, scoutReason, scoutPlayers = [{ user_id: 1, name: 'Новое имя Арены', external_uuid: 'arena-1' }] } = {}) {
  const writes = [];
  const lands = [{ id: 3, name: 'Арнор', owner_clan_id: 8, is_playable: true, adjacent_territory_ids: [4] }, { id: 4, name: 'Форност', owner_clan_id: 7, is_playable: true, adjacent_territory_ids: [3] }];
  const planning = { cycle_id: 1, clan_id: 7, clan_name: 'Демо', phase: 'preparation', editable: true, snapshot_ready: true,
    server_time: new Date().toISOString(), battle_at: new Date(Date.now() + 86400000).toISOString(),
    plan: { revision: 2, orders: [{ user_id: 2, kind: 'reserve', territory_id: null, source_id: null, route: 'land' }] },
    members: [{ user_id: 1, name: 'Новое имя Арены', eligible: true }, { user_id: 2, name: 'Резервист', eligible: true }],
    limits: { attacks: 2, reserves: 2, ambush_players: 2 }, territories: lands, defence_targets: [4],
    attack_routes: [{ territory_id: 3, source_id: 4, route: 'land' }] };
  const preparation = { cycle_id: 1, clan_id: 7, clan_name: 'Демо', phase: 'preparation', territories: lands,
    scout: { price: '200', cutoff: new Date(Date.now() + 64800000).toISOString(), can_request: scoutAvailable, unavailable_reason: scoutReason, players: scoutPlayers, request: null, report: null, wallet_revision: 5 }, startup: { ready: false } };
  await page.addInitScript(() => localStorage.setItem('language', 'ru'));
  await page.route('**/api/**', route => {
    const path = new URL(route.request().url()).pathname;
    let json = {};
    if (path.endsWith('/auth/session') || path.endsWith('/users/me')) json = { id: 1, username: 'Глава', language: 'ru', is_claimed: true, is_verified: true, onboarding_completed: true, role: { name: 'admin' } };
    else if (path.endsWith('/clans/my')) json = { id: 7, leader_id: 1, name: 'Демо' };
    else if (path.endsWith('/cycles/current')) json = { mechanics_version: 'cycle_v1', cycle: { id: 1 }, territory_battles: [] };
    else if (path.endsWith('/cycles/1/map')) json = { cycle_id: 1, clan_id: 7, phase: 'preparation', ready: false, can_command: false, battles: [], dispatches: [], ambushes: [], requests: [], help_targets: [], allied_targets: [], territories: [] };
    else if (path === '/api/v1/territories/') json = lands;
    else if (path === '/api/v1/clans/') json = [{ id: 7, name: 'Демо' }, { id: 8, name: 'Соседи' }];
    else if (path.endsWith('/planning')) json = planning;
    else if (path.endsWith('/preparation')) json = preparation;
    else if (path.endsWith('/plan') || path.endsWith('/scout')) {
      const body = route.request().postDataJSON(); writes.push({ path, body });
      if (path.endsWith('/plan')) { planning.plan = { revision: 3, orders: body.orders }; json = planning.plan; }
      else { preparation.scout.can_request = false; preparation.scout.request = { id: 10, territory_id: body.territory_id, scout_user_id: body.scout_user_id, scout_uuid: 'arena-1', scout_name: 'Новое имя Арены' }; json = preparation.scout.request; }
    } else if (path.includes('notifications')) json = { items: [], unread_count: 0 };
    else if (path.includes('presence')) json = { items: [] };
    else if (path.includes('localization') || path.includes('diplomacy') || path.endsWith('/wars/active/')) json = [];
    return route.fulfill({ json });
  });
  await page.setViewportSize({ width: 1440, height: 1000 });
  await page.goto('/map');
  const land = page.getByRole('button', { name: 'Арнор', exact: true });
  await expect(land).toHaveAttribute('tabindex', '0');
  await land.press('Enter');
  await expect(page.locator('.cycle-map-panel')).toBeVisible();
  return writes;
}

test('orders are confirmed directly on the selected map territory without losing other assignments', async ({ page }) => {
  const writes = await setup(page);
  await page.getByRole('button', { name: 'Распределить отряд', exact: true }).click();
  const dialog = page.getByRole('dialog').first();
  await expect(dialog).toContainText('Арнор');
  await dialog.getByRole('checkbox', { name: /Новое имя Арены/ }).check();
  await dialog.getByRole('button', { name: 'Проверить приказ', exact: true }).click();
  expect(writes).toHaveLength(0);
  await page.getByRole('dialog', { name: 'Подтвердить приказ' }).getByRole('button', { name: 'Подтвердить', exact: true }).click();
  await expect.poll(() => writes.length).toBe(1);
  expect(writes[0].body).toEqual({ expected_revision: 2, orders: [
    { user_id: 2, kind: 'reserve', territory_id: null, source_id: null, route: 'land' },
    { user_id: 1, source_id: 4, territory_id: 3, route: 'land', kind: 'attack' },
  ] });
  await expect(page).toHaveURL(/\/map$/);
});

test('scouting on the map fixes the paid target and displays the return time', async ({ page }) => {
  const writes = await setup(page);
  await page.getByRole('button', { name: 'Разведать территорию', exact: true }).click();
  const dialog = page.getByRole('dialog').first();
  await expect(dialog).toContainText('200');
  await expect(dialog.getByRole('button', { name: 'Заказать разведку', exact: true })).toBeDisabled();
  await dialog.getByRole('combobox', { name: 'Разведчик', exact: true }).selectOption('1');
  await dialog.getByRole('button', { name: 'Заказать разведку', exact: true }).click();
  const confirmation = page.getByRole('dialog', { name: 'Заказать разведку', exact: true });
  await expect(confirmation).toContainText('Новое имя Арены');
  await expect(confirmation).toContainText('до конца цикла');
  await confirmation.getByRole('button', { name: 'Подтвердить', exact: true }).click();
  await expect.poll(() => writes.length).toBe(1);
  expect(writes[0].body).toEqual({ territory_id: 3, scout_user_id: 1, expected_revision: 5 });
  await expect(dialog).toContainText('Разведчики ещё не вернулись');
  await expect(dialog).toContainText('Новое имя Арены');
  await expect(dialog).toContainText('до конца цикла');
  await expect(dialog.getByRole('combobox', { name: 'Разведчик', exact: true })).toHaveCount(0);
  await expect(dialog.getByRole('button', { name: 'Заказать разведку', exact: true })).toHaveCount(0);
  await expect(page).toHaveURL(/\/map$/);
});

test('scouting without a free verified member cannot be ordered', async ({ page }) => {
  const writes = await setup(page, { scoutPlayers: [] });
  await page.getByRole('button', { name: 'Разведать территорию', exact: true }).click();
  const dialog = page.getByRole('dialog').first();
  await expect(dialog).toContainText('Нет свободных подтверждённых игроков');
  await expect(dialog.getByRole('button', { name: 'Заказать разведку', exact: true })).toBeDisabled();
  expect(writes).toEqual([]);
});

test('server no-free-player restriction explains how to free a scout', async ({ page }) => {
  const writes = await setup(page, { scoutAvailable: false, scoutPlayers: [], scoutReason: 'no_free_players' });
  await page.getByRole('button', { name: 'Разведать территорию', exact: true }).click();
  const dialog = page.getByRole('dialog').first();
  await expect(dialog).toContainText('Нет свободного игрока');
  await expect(dialog).toContainText('снимите');
  await expect(dialog).toContainText('назначение в отрядах');
  await expect(dialog.getByRole('button', { name: 'Заказать разведку', exact: true })).toHaveCount(0);
  expect(writes).toEqual([]);
});

for (const change of ['member', 'wallet']) {
  test(`scout confirmation rejects stale ${change} after map polling`, async ({ page }) => {
    const writes = await setup(page);
    await page.clock.install();
    await page.getByRole('button', { name: 'Разведать территорию', exact: true }).click();
    const dialog = page.getByRole('dialog').first();
    await dialog.getByRole('combobox', { name: 'Разведчик', exact: true }).selectOption('1');
    await dialog.getByRole('button', { name: 'Заказать разведку', exact: true }).click();
    await page.route('**/preparation', route => route.fulfill({ json: {
      cycle_id: 1, clan_id: 7, territories: [{ id: 3, name: 'Арнор' }],
      scout: { can_request: true, cutoff: '2099-01-01T00:00:00Z', wallet_revision: change === 'wallet' ? 6 : 5,
        players: change === 'member' ? [] : [{ user_id: 1, name: 'Новое имя Арены', external_uuid: 'arena-1' }], request: null },
      startup: { ready: false },
    } }));
    await page.clock.fastForward(15001);
    const confirmation = page.getByRole('dialog', { name: 'Заказать разведку', exact: true });
    await expect(confirmation.getByRole('button', { name: 'Подтвердить', exact: true })).toBeDisabled();
    await expect(confirmation).toContainText('Выберите разведчика заново');
    await confirmation.getByRole('button', { name: 'Отмена', exact: true }).click();
    await expect(dialog.getByRole('combobox', { name: 'Разведчик', exact: true })).toHaveValue('');
    expect(writes).toEqual([]);
  });
}

test('unavailable scouting shows an explanation instead of an empty block', async ({ page }) => {
  await setup(page, { scoutAvailable: false });
  await page.getByRole('button', { name: 'Разведать территорию', exact: true }).click();
  await expect(page.getByRole('dialog').first()).toContainText('Разведку заказывают глава или воевода');
});

for (const [reason, message] of [
  ['no_permission', 'Разведку заказывают глава или воевода клана'],
  ['outside_preparation', 'только во время подготовки'],
  ['cutoff_passed', 'Приём заказов разведки завершён'],
  ['already_requested', 'Разведка уже заказана'],
  ['economy_missing', 'казна нового сезона ещё не открыта'],
]) {
  test(`scouting explains server restriction ${reason}`, async ({ page }) => {
    await setup(page, { scoutAvailable: false, scoutReason: reason, scoutPlayers: [] });
    await page.getByRole('button', { name: 'Разведать территорию', exact: true }).click();
    const dialog = page.getByRole('dialog').first();
    await expect(dialog).toContainText(message);
    await expect(dialog).not.toContainText(reason);
  });
}

test('reinforcement players and origin are confirmed without leaving the map', async ({ page }) => {
  await setup(page);
  const data = { cycle_id: 1, clan_id: 7, clan_name: 'Демо', ready: true, can_command: true, phase: 'battle',
    server_time: new Date().toISOString(), command_deadline: new Date(Date.now() + 86400000).toISOString(),
    players: [{ user_id: 2, name: 'Резервист', available: true }], names: [{ user_id: 2, name: 'Резервист' }],
    origins: [{ territory_id: 4, name: 'Форност' }], route_previews: [], own_targets: [{ territory_id: 3, battle_id: 50 }, { territory_id: 4, battle_id: 51 }], help_targets: [3, 4], allied_targets: [],
    territories: [{ id: 3, name: 'Арнор' }, { id: 4, name: 'Форност' }], clans: [{ id: 7, name: 'Демо' }],
    state: { revision: 3, reserves: [], requests: [], dispatches: [], ambushes: [] } };
  const commands = [];
  await page.route('**/reinforcements/context', route => route.fulfill({ json: data }));
  await page.route('**/reinforcements/dispatches', route => {
    const body = route.request().postDataJSON(); commands.push(body);
    data.players[0].available = false; data.state.revision++;
    data.state.dispatches.push({ id: body.dispatch_id, sender_clan_id: 7, recipient_clan_id: 7, territory_id: 3, player_user_ids: [2], sent_at: data.server_time, arrives_at: new Date(Date.now() + 86400000).toISOString(), outcome: 'clear' });
    return route.fulfill({ json: data.state });
  });
  await page.getByRole('button', { name: 'Отправить подкрепление', exact: true }).click();
  const dialog = page.getByRole('dialog').first();
  await expect(dialog.getByRole('combobox', { name: 'Куда отправить' })).toHaveValue('7:3:');
  await expect(dialog.locator('.cr-help-list')).not.toContainText('Форност');
  await dialog.getByRole('checkbox', { name: 'Резервист', exact: true }).check();
  await dialog.getByRole('combobox', { name: 'Земля отправления', exact: true }).selectOption('4');
  await dialog.getByRole('button', { name: 'Отправить подкрепление', exact: true }).click();
  expect(commands).toHaveLength(0);
  await page.getByRole('dialog').last().getByRole('button', { name: 'Отправить', exact: true }).click();
  await expect.poll(() => commands.length).toBe(1);
  expect(commands[0]).toMatchObject({ territory_id: 3, origin_territory_id: 4, recipient_clan_id: 7, request_id: null, player_user_ids: [2], expected_revision: 3 });
  await expect(dialog.locator('.cr-dispatch')).toContainText('Резервист');
  await expect(page).toHaveURL(/\/map$/);
});

test('an open scouting dialog receives the numeric report without reopening', async ({ page }) => {
  await setup(page);
  await page.clock.install();
  let ready = false;
  await page.route('**/preparation', route => route.fulfill({ json: {
    cycle_id: 1, clan_id: 7, clan_name: 'Демо', territories: [{ id: 3, name: 'Арнор' }],
    scout: { can_request: false, players: [], cutoff: new Date().toISOString(), request: { id: 1, territory_id: 3, scout_user_id: 1, scout_uuid: 'arena-1', scout_name: 'Новое имя Арены' }, report: ready ? { enemy_squads: [3, 2] } : null }, startup: { ready: false },
  } }));
  await page.getByRole('button', { name: 'Разведать территорию', exact: true }).click();
  const dialog = page.getByRole('dialog').first();
  await expect(dialog).toContainText('Разведчики ещё не вернулись');
  ready = true;
  await page.clock.fastForward(15001);
  await expect(dialog.locator('.cp-report')).toContainText('3');
  await expect(dialog.locator('.cp-report')).toContainText('2');
});
