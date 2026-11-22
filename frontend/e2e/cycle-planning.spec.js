import { test, expect } from '@playwright/test';

const user = { id: 1, username: 'Head', language: 'ru', is_verified: true, is_claimed: true,
  role: { name: 'user' }, onboarding_completed: true };
const context = () => ({ cycle_id: 1, clan_id: 7, clan_name: 'Akatsuki', phase: 'preparation',
  editable: true, snapshot_ready: true, server_time: '2026-10-17T12:00:00Z', battle_at: '2026-10-18T12:00:00Z',
  plan: { revision: 0, orders: [], warnings: [], frozen_at: null },
  limits: { attacks: 2, reserves: 1, ambush_players: 2 },
  members: [{ user_id: 1, name: 'Head', eligible: true }, { user_id: 2, name: 'Renamed player', eligible: true },
    { user_id: 3, name: 'Cooldown player', eligible: true, reserve_blocked: true }],
  territories: [{ id: 10, name: 'Home' }, { id: 20, name: 'Evendim' }], defence_targets: [10],
  attack_routes: [{ territory_id: 20, source_id: 10, route: 'land' }, { territory_id: 20, source_id: 10, route: 'sea' }] });

async function mock(page, data, { conflict = false, clanless = false } = {}) {
  const writes = [];
  await page.addInitScript(() => localStorage.setItem('language', 'ru'));
  await page.route('**/api/v1/**', async route => {
    const request = route.request(), path = new URL(request.url()).pathname;
    let payload = {};
    if (path.endsWith('/auth/session') || path.endsWith('/users/me')) payload = user;
    else if (path.endsWith('/clans/my')) {
      if (clanless) return route.fulfill({ status: 404, json: { detail: 'No clan' } });
      payload = { id: 7, name: 'Akatsuki', leader_id: 1 };
    } else if (path.endsWith('/planning')) payload = data;
    else if (path.endsWith('/plan') && request.method() === 'PUT') {
      writes.push(request.postDataJSON());
      if (conflict) return route.fulfill({ status: 409, json: { detail: 'Plan changed' } });
      data.plan = { ...data.plan, revision: data.plan.revision + 1, orders: request.postDataJSON().orders };
      payload = data.plan;
    } else if (path.includes('notifications')) payload = { items: [], unread_count: 0, total: 0 };
    else if (path.includes('presence')) payload = { items: [] };
    else if (path.includes('localization')) payload = [];
    return route.fulfill({ json: payload });
  });
  return writes;
}

test('group selection assigns an entire squad locally before explicit saving', async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 1000 });
  const writes = await mock(page, context());
  await page.goto('/campaign/cycles/1/orders');
  await page.getByRole('checkbox', { name: 'Выбрать игрока Head', exact: true }).check();
  await page.getByRole('checkbox', { name: 'Выбрать игрока Renamed player', exact: true }).check();
  const composer = page.getByRole('group', { name: 'Назначение отряда', exact: true });
  await composer.getByRole('combobox', { name: 'Назначение', exact: true }).selectOption('attack');
  await composer.getByRole('combobox', { name: 'Территория и маршрут' }).selectOption('20:10:land');
  await composer.getByRole('button', { name: 'Назначить выбранных' }).click();
  expect(writes).toEqual([]);
  await expect(page.locator('.co-squad-list')).toContainText('Evendim');
  await expect(page.locator('.co-squad-list')).toContainText('Renamed player');
  expect(await page.locator('.co-roster').evaluate(roster => [...roster.querySelectorAll('.co-fields select')].every(select => select.getBoundingClientRect().right <= roster.getBoundingClientRect().right + 1))).toBe(true);
  const search = page.getByRole('searchbox', { name: 'Поиск игрока', exact: true });
  await search.fill('Head');
  await search.press('Enter');
  await page.waitForTimeout(200);
  expect(writes).toEqual([]);
  await search.fill('');
  await page.getByRole('button', { name: 'Сохранить план', exact: true }).click();
  await expect.poll(() => writes.length).toBe(1);
  expect(writes[0].orders).toHaveLength(2);
  expect(writes[0].orders.every(row => row.kind === 'attack' && row.territory_id === 20)).toBe(true);
  await page.screenshot({ path: 'test-results/squad-board-desktop.png', fullPage: true });
});

for (const width of [390, 1440]) {
  test(`head assigns by stable id and saves route and reserve at ${width}px`, async ({ page }) => {
    await page.setViewportSize({ width, height: 1000 });
    const writes = await mock(page, context());
    const errors = [];
    page.on('pageerror', error => errors.push(error.message));
    await page.goto('/campaign/cycles/1/orders');
    const head = page.getByRole('group', { name: 'Head', exact: true });
    const renamed = page.getByRole('group', { name: 'Renamed player', exact: true });
    await head.getByRole('combobox', { name: 'Назначение', exact: true }).selectOption('reserve');
    await renamed.getByRole('combobox', { name: 'Назначение', exact: true }).selectOption('attack');
    await renamed.getByRole('combobox', { name: 'Территория и маршрут' }).selectOption('20:10:sea');
    await expect(page.getByRole('group', { name: 'Cooldown player' }).getByRole('option', { name: 'Запас', exact: true })).toHaveAttribute('disabled', '');
    await page.getByRole('button', { name: 'Сохранить план', exact: true }).click();
    await expect(page.getByRole('status')).toContainText('План сохранён');
    expect(writes).toHaveLength(1);
    expect(writes[0].expected_revision).toBe(0);
    expect(writes[0].orders).toContainEqual({ user_id: 2, kind: 'attack', territory_id: 20, source_id: 10, route: 'sea' });
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    expect(errors).toEqual([]);
    await page.evaluate(() => window.scrollTo({ top: 0, behavior: 'instant' }));
    await expect(page.getByRole('heading', { name: 'Распределение отрядов' })).toBeInViewport();
    await page.screenshot({ path: `test-results/cycle-planning-${width}.png`, fullPage: true });
  });
}

test('ordinary member sees read-only assignments', async ({ page }) => {
  await mock(page, { ...context(), editable: false });
  await page.goto('/campaign/cycles/1/orders');
  await expect(page.getByRole('heading', { name: 'Распределение отрядов' })).toBeVisible();
  await expect(page.getByRole('button', { name: 'Сохранить план' })).toHaveCount(0);
  await expect(page.getByRole('combobox')).toHaveCount(0);
  await expect(page.getByRole('group', { name: 'Head', exact: true })).toContainText('Без назначения');
});

test('scout status explains the cycle lock and prevents new assignments', async ({ page }) => {
  const data = context();
  data.members[1] = { ...data.members[1], eligible: false, scouting: true };
  const writes = await mock(page, data);
  await page.goto('/campaign/cycles/1/orders');
  const row = page.getByRole('group', { name: 'Renamed player', exact: true });
  await expect(row).toContainText('Разведчик до конца цикла');
  await expect(row).not.toContainText('Без назначения');
  await expect(row.getByRole('combobox')).toHaveCount(0);
  expect(writes).toEqual([]);
});

test('revision conflict retains draft and reload requires confirmation', async ({ page }) => {
  await mock(page, context(), { conflict: true });
  await page.goto('/campaign/cycles/1/orders');
  const select = page.getByRole('group', { name: 'Head', exact: true }).getByRole('combobox', { name: 'Назначение', exact: true });
  await select.selectOption('reserve');
  await page.getByRole('button', { name: 'Сохранить план' }).click();
  await expect(page.getByRole('alert')).toContainText('Ваш вариант сохранён');
  await expect(select).toHaveValue('reserve');
  await expect(page.getByRole('button', { name: 'Сохранить план' })).toBeDisabled();
  await page.getByRole('button', { name: 'Обновить', exact: true }).click();
  await expect(page.getByRole('dialog')).toBeVisible();
  await page.getByRole('button', { name: 'Отмена', exact: true }).click();
  await expect(select).toHaveValue('reserve');
  await page.getByRole('button', { name: 'Обновить', exact: true }).click();
  await page.getByRole('dialog').getByRole('button', { name: 'Обновить', exact: true }).click();
  await expect(select).toHaveValue('');
});

test('clanless player sees an empty state, not another clan plan', async ({ page }) => {
  await mock(page, context(), { clanless: true });
  await page.goto('/campaign/cycles/1/orders');
  await expect(page.getByText('Для просмотра плана нужно состоять в клане.', { exact: true })).toBeVisible();
  await expect(page.getByRole('combobox')).toHaveCount(0);
});

test('background revision change and freeze preserve draft but block writes', async ({ page }) => {
  await page.clock.install();
  const data = context();
  const writes = await mock(page, data);
  await page.goto('/campaign/cycles/1/orders');
  const select = page.getByRole('group', { name: 'Head', exact: true }).getByRole('combobox', { name: 'Назначение', exact: true });
  await select.selectOption('reserve');
  data.plan.revision = 1;
  await page.clock.fastForward(30_000);
  await expect(page.getByRole('alert')).toContainText('Ваш вариант сохранён');
  await expect(select).toHaveValue('reserve');
  await expect(page.getByRole('button', { name: 'Сохранить план' })).toBeDisabled();
  data.editable = false; data.phase = 'battle';
  await page.clock.fastForward(30_000);
  await expect(page.getByRole('button', { name: 'Сохранить план' })).toHaveCount(0);
  await expect(page.getByRole('group', { name: 'Head', exact: true }).locator('.co-assignment')).toHaveText('Запас');
  expect(writes).toEqual([]);
});

test('local server-time deadline blocks editing without waiting for a poll', async ({ page }) => {
  await page.clock.install();
  const data = context();
  data.battle_at = '2026-10-17T12:00:05Z';
  const writes = await mock(page, data);
  await page.goto('/campaign/cycles/1/orders');
  const select = page.getByRole('group', { name: 'Head', exact: true }).getByRole('combobox', { name: 'Назначение', exact: true });
  await select.selectOption('reserve');
  await page.clock.fastForward(5001);
  await expect(select).toBeDisabled();
  await expect(page.getByRole('button', { name: 'Сохранить план' })).toBeDisabled();
  expect(writes).toEqual([]);
});

test('metadata response started before saving cannot roll back the saved revision', async ({ page }) => {
  const data = context();
  const writes = await mock(page, data);
  await page.clock.install();
  await page.goto('/campaign/cycles/1/orders');
  const select = page.getByRole('group', { name: 'Head', exact: true }).getByRole('combobox', { name: 'Назначение', exact: true });
  await select.selectOption('reserve');
  let release;
  const gate = new Promise(resolve => { release = resolve; });
  const old = structuredClone(data);
  await page.route('**/planning', async route => { await gate; await route.fulfill({ json: old }); });
  const requested = page.waitForRequest('**/planning');
  await page.clock.fastForward(30_000);
  await requested;
  await page.getByRole('button', { name: 'Сохранить план' }).click();
  await expect(page.getByRole('status')).toContainText('План сохранён');
  const response = page.waitForResponse('**/planning');
  release();
  await response;
  await expect(select).toHaveValue('reserve');
  await select.selectOption('');
  await page.getByRole('button', { name: 'Сохранить план' }).click();
  await expect.poll(() => writes.length).toBe(2);
  expect(writes[1].expected_revision).toBe(1);
});

test('frozen assignments remain readable when a route is no longer available', async ({ page }) => {
  const data = context();
  data.editable = false; data.phase = 'battle';
  data.plan = { revision: 1, orders: [{ user_id: 2, kind: 'attack', territory_id: 20, source_id: 10, route: 'sea' }], warnings: [], frozen_at: data.battle_at };
  data.attack_routes = [];
  await mock(page, data);
  await page.goto('/campaign/cycles/1/orders');
  const row = page.getByRole('group', { name: 'Renamed player', exact: true });
  await expect(row).toContainText('Evendim');
  await expect(row).toContainText('по морю');
});

test('lost membership clears private plan instead of showing cached assignments', async ({ page }) => {
  await page.clock.install();
  await mock(page, context());
  await page.goto('/campaign/cycles/1/orders');
  await expect(page.getByRole('heading', { name: 'Akatsuki' })).toBeVisible();
  await page.route('**/planning', route => route.fulfill({ status: 403, json: { detail: 'Membership required' } }));
  await page.clock.fastForward(30_000);
  await expect(page.getByRole('alert')).toBeVisible();
  await expect(page.getByRole('group', { name: 'Renamed player' })).toHaveCount(0);
});

test('explicit refresh prevents editing while replacement is pending', async ({ page }) => {
  await mock(page, context());
  await page.goto('/campaign/cycles/1/orders');
  const select = page.getByRole('group', { name: 'Head', exact: true }).getByRole('combobox', { name: 'Назначение', exact: true });
  await expect(select).toBeEnabled();
  let release;
  const gate = new Promise(resolve => { release = resolve; });
  await page.route('**/planning', async route => { await gate; await route.fulfill({ json: context() }); });
  await page.getByRole('button', { name: 'Обновить', exact: true }).click();
  await expect(select).toBeDisabled();
  release();
  await expect(select).toBeEnabled();
});

test('clean viewer adopts reveal changes even without a new plan revision', async ({ page }) => {
  await page.clock.install();
  const data = context();
  data.plan = { revision: 1, orders: [{ user_id: 1, kind: 'reserve' }], warnings: [], frozen_at: null };
  await mock(page, data);
  await page.goto('/campaign/cycles/1/orders');
  await expect(page.getByRole('group', { name: 'Head', exact: true }).getByRole('combobox')).toHaveValue('reserve');
  data.editable = false; data.phase = 'battle'; data.plan.orders = []; data.plan.frozen_at = data.battle_at;
  await page.clock.fastForward(30_000);
  const row = page.getByRole('group', { name: 'Head', exact: true });
  await expect(row.locator('.co-assignment')).toHaveText('Без назначения');
  await expect(row.getByRole('combobox')).toHaveCount(0);
});

test('departed draft-only player remains removable without discarding other edits', async ({ page }) => {
  await page.clock.install();
  const data = context();
  await mock(page, data);
  await page.goto('/campaign/cycles/1/orders');
  const head = page.getByRole('group', { name: 'Head', exact: true }).getByRole('combobox', { name: 'Назначение', exact: true });
  const player = page.getByRole('group', { name: 'Renamed player', exact: true }).getByRole('combobox', { name: 'Назначение', exact: true });
  await head.selectOption('reserve');
  await player.selectOption('defend');
  await page.getByRole('group', { name: 'Renamed player', exact: true }).getByRole('combobox', { name: 'Территория и маршрут' }).selectOption('10');
  data.members = data.members.filter(m => m.user_id !== 2);
  await page.clock.fastForward(30_000);
  await expect(page.getByRole('alert')).toContainText('недоступных игроков');
  await player.selectOption('');
  await expect(head).toHaveValue('reserve');
  await expect(page.getByRole('button', { name: 'Сохранить план' })).toBeEnabled();
});

test('successful null clan response clears the former clan plan', async ({ page }) => {
  await page.clock.install();
  await mock(page, context());
  await page.goto('/campaign/cycles/1/orders');
  await expect(page.getByRole('heading', { name: 'Akatsuki' })).toBeVisible();
  await page.route('**/clans/my', route => route.fulfill({ json: null }));
  await page.clock.fastForward(30_000);
  await expect(page.getByText('Для просмотра плана нужно состоять в клане.', { exact: true })).toBeVisible();
  await expect(page.getByRole('combobox')).toHaveCount(0);
});
