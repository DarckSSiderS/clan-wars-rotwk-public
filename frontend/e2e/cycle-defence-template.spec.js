import { test, expect } from '@playwright/test';

const user = { id: 1, username: 'Head', language: 'ru', is_verified: true, is_claimed: true,
  role: { name: 'user' }, onboarding_completed: true };
const context = () => ({ cycle_id: 1, clan_id: 7, clan_name: 'Akatsuki', phase: 'preparation',
  editable: true, snapshot_ready: true, server_time: '2026-10-17T12:00:00Z', battle_at: '2026-10-18T12:00:00Z',
  plan: { revision: 0, orders: [], warnings: [], frozen_at: null },
  limits: { attacks: 2, reserves: 1, ambush_players: 2 },
  members: [{ user_id: 1, name: 'Head', eligible: true }, { user_id: 2, name: 'Renamed player', eligible: true }],
  territories: [{ id: 10, name: 'Home' }, { id: 20, name: 'Evendim' }], defence_targets: [10], attack_routes: [],
  defence_template: { revision: 0, editable: true, assignments: [], member_ids: [1, 2],
    targets: [{ id: 10, name: 'Home' }], fallback_orders: [] } });

async function mock(page, data, conflict = false) {
  const writes = [], plans = [];
  await page.addInitScript(() => localStorage.setItem('language', 'ru'));
  await page.route('**/api/v1/**', async route => {
    const request = route.request(), path = new URL(request.url()).pathname;
    let payload = {};
    if (path.endsWith('/auth/session') || path.endsWith('/users/me')) payload = user;
    else if (path.endsWith('/clans/my')) payload = { id: 7, name: 'Akatsuki', leader_id: 1 };
    else if (path.endsWith('/planning')) payload = structuredClone(data);
    else if (path.endsWith('/defence-template')) {
      if (request.method() === 'PUT') {
        writes.push(request.postDataJSON());
        if (conflict) return route.fulfill({ status: 409, json: { detail: 'Changed' } });
        data.defence_template = { ...data.defence_template, revision: data.defence_template.revision + 1,
          assignments: request.postDataJSON().assignments };
      }
      payload = data.defence_template;
    } else if (path.endsWith('/plan')) { plans.push(request.postDataJSON()); payload = data.plan; }
    else if (path.includes('notifications')) payload = { items: [], unread_count: 0, total: 0 };
    else if (path.includes('presence')) payload = { items: [] };
    else if (path.includes('localization')) payload = [];
    return route.fulfill({ json: payload });
  });
  return { writes, plans };
}

for (const width of [390, 1440]) {
  test(`template saves stable ids separately from manual orders at ${width}px`, async ({ page }) => {
    await page.setViewportSize({ width, height: 1000 });
    const { writes, plans } = await mock(page, context());
    await page.goto('/campaign/cycles/1/orders');
    const panel = page.getByRole('region', { name: 'Защитный шаблон', exact: true });
    await panel.getByRole('combobox', { name: 'Защита Renamed player', exact: true }).selectOption('10');
    expect(writes).toEqual([]);
    await panel.getByRole('button', { name: 'Сохранить шаблон', exact: true }).click();
    await expect(panel.getByRole('status')).toContainText('Шаблон сохранён');
    expect(writes).toEqual([{ expected_revision: 0, assignments: [{ user_id: 2, territory_id: 10 }] }]);
    expect(plans).toEqual([]);
    await expect(page.getByRole('group', { name: 'Renamed player', exact: true }).getByRole('combobox', { name: 'Назначение', exact: true })).toHaveValue('');
    await panel.getByRole('combobox', { name: 'Защита Renamed player', exact: true }).selectOption('');
    await panel.getByRole('button', { name: 'Сохранить шаблон', exact: true }).click();
    await expect.poll(() => writes.length).toBe(2);
    expect(writes[1]).toEqual({ expected_revision: 1, assignments: [] });
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    await page.screenshot({ path: `test-results/defence-template-${width}.png`, fullPage: true });
  });
}

test('CAS conflict and polling retain template draft; reload is explicit', async ({ page }) => {
  await page.clock.install();
  const data = context();
  const { writes } = await mock(page, data, true);
  await page.goto('/campaign/cycles/1/orders');
  const panel = page.getByRole('region', { name: 'Защитный шаблон', exact: true });
  const select = panel.getByRole('combobox', { name: 'Защита Head', exact: true });
  await select.selectOption('10');
  await panel.getByRole('button', { name: 'Сохранить шаблон', exact: true }).click();
  await expect(panel.getByRole('alert')).toContainText('Ваш вариант сохранён');
  await expect(select).toHaveValue('10');
  data.defence_template.revision = 2;
  await page.clock.fastForward(30_000);
  await expect(select).toHaveValue('10');
  await expect(panel.getByRole('button', { name: 'Сохранить шаблон', exact: true })).toBeDisabled();
  await panel.getByRole('button', { name: 'Обновить шаблон', exact: true }).click();
  await expect(page.getByRole('dialog')).toBeVisible();
  await page.getByRole('dialog').getByRole('button', { name: 'Обновить', exact: true }).click();
  await expect(select).toHaveValue('');
  expect(writes).toHaveLength(1);
});

test('rest template stays editable without preparation snapshot; members read only', async ({ page }) => {
  const data = context();
  data.editable = false; data.phase = 'rest'; data.snapshot_ready = false;
  data.battle_at = '2026-10-16T12:00:00Z';
  await mock(page, data);
  await page.goto('/campaign/cycles/1/orders');
  const panel = page.getByRole('region', { name: 'Защитный шаблон', exact: true });
  await expect(panel.getByRole('combobox', { name: 'Защита Head', exact: true })).toBeEnabled();
  data.defence_template.editable = false;
  await page.reload();
  await expect(panel.getByRole('combobox')).toHaveCount(0);
  await expect(panel.getByRole('button', { name: 'Сохранить шаблон', exact: true })).toHaveCount(0);
});

test('server-time boundary blocks template writes before poll', async ({ page }) => {
  await page.clock.install();
  const data = context();
  data.battle_at = '2026-10-17T12:00:05Z';
  await mock(page, data);
  await page.goto('/campaign/cycles/1/orders');
  const panel = page.getByRole('region', { name: 'Защитный шаблон', exact: true });
  const select = panel.getByRole('combobox', { name: 'Защита Head', exact: true });
  await select.selectOption('10');
  await page.clock.fastForward(5001);
  await expect(select).toBeDisabled();
  await expect(panel.getByRole('button', { name: 'Сохранить шаблон', exact: true })).toBeDisabled();
});

test('rest deadline blocks template writes without waiting for a poll', async ({ page }) => {
  await page.clock.install();
  const data = context();
  data.phase = 'rest'; data.editable = false;
  data.battle_at = '2026-10-16T12:00:00Z';
  data.defence_template.editable_until = '2026-10-17T12:00:05Z';
  await mock(page, data);
  await page.goto('/campaign/cycles/1/orders');
  const panel = page.getByRole('region', { name: 'Защитный шаблон', exact: true });
  const select = panel.getByRole('combobox', { name: 'Защита Head', exact: true });
  await select.selectOption('10');
  await page.clock.fastForward(5001);
  await expect(select).toBeDisabled();
  await expect(panel.getByRole('button', { name: 'Сохранить шаблон', exact: true })).toBeDisabled();
});
