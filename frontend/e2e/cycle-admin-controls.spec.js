import { test, expect } from '@playwright/test';

const user = { id: 1, username: 'Head', language: 'ru', is_verified: true, is_claimed: true,
  role: { name: 'admin' }, onboarding_completed: true };
const now = '2026-10-31T12:00:00Z';

async function mock(page, { recovery = false, mode = 'cycle_v1', loseFirst = false } = {}) {
  const writes = [], paths = [];
  const state = { state_id: 1, season_id: 2, clan_id: 11, revision: 4,
    wallet: { gold: '1234.123456789012', iron: '40', wood: '30', food: '20', mithril: '5' } };
  await page.addInitScript(() => localStorage.setItem('language', 'ru'));
  await page.route('**/api/v1/**', async route => {
    const request = route.request(), path = new URL(request.url()).pathname;
    paths.push(path);
    let json = {};
    if (path.endsWith('/auth/session') || path.endsWith('/users/me')) json = user;
    else if (path === '/api/v1/admin/overview') json = { campaign: { owned_territories: 3, territories: 76, active_wars: 0, active_caravans: 0 },
      clans: { total: 1, members: 4 }, users: { registered: 4, blocked: 0, active: 4 }, matches: { total: 12, sync_errors: 0 } };
    else if (path === '/api/v1/admin/clans') json = { clans: [{ id: 11, name: 'Akatsuki', members: 4, territories: 3,
      gold: 999, iron: 1, wood: 1, food: 1, mithril: 1, influence: 100 }] };
    else if (path === '/api/v1/campaign/seasons') json = [{ id: 2, number: 2, name: 'Проверка', status: 'active' }];
    else if (path === '/api/v1/wars/active/') json = [];
    else if (path === '/api/v1/campaign/cycles/admin/diagnostics') json = { server_time: now, mechanics_version: mode, season_id: 2,
      cycle: { id: 7, number: 2, revision: 8, phase: 'settlement', recovery_available: recovery },
      arena: { last_complete_scan: null, heartbeat_at: now, last_worker_success_at: now, worker_failures: 0,
        pending_contributions: [{ reason: 'missing_historical_elo', count: 2 }], pending_source_replays: 1, pending_interceptions: 0 } };
    else if (path === '/api/v1/campaign/cycles/admin/cycles/7/recover-preparation') {
      writes.push(request.postDataJSON()); recovery = false;
      json = { cycle_id: 7, revision: 9, preparation_at: now, battle_at: '2026-11-01T12:00:00Z' };
    } else if (path === '/api/v1/admin/clans/11/cycle-economy') {
      if (request.method() === 'PATCH') {
        writes.push(request.postDataJSON());
        if (loseFirst && writes.length === 1) return route.abort('failed');
        json = { ...state, revision: 5, wallet: request.postDataJSON().wallet };
      } else json = { mechanics_version: mode, season_id: 2, state: mode === 'cycle_v1' ? state : null };
    } else if (path === '/api/v1/admin/clans/11/economy') { writes.push(request.postDataJSON()); }
    else if (path.includes('notifications')) json = { items: [], unread_count: 0, total: 0 };
    else if (path.includes('presence')) json = { items: [] };
    else if (path.includes('localization')) json = [];
    else if (path.includes('/clans/my')) return route.fulfill({ status: 404, json: { detail: 'Нет клана' } });
    else if (path.includes('admin/feedback')) json = { tickets: [], unread_count: 0 };
    else if (/\/cycles\/admin\//.test(path)) return route.fulfill({ status: 404, json: { detail: 'Неверный адрес' } });
    return route.fulfill({ json });
  });
  return { writes, paths };
}

test('admin diagnostics uses campaign API and requires explicit recovery confirmation', async ({ page }) => {
  const { writes, paths } = await mock(page, { recovery: true });
  await page.goto('/admin');
  const panel = page.locator('.admin-cycle-diagnostics');
  await expect(panel).toBeVisible();
  await expect(panel).toContainText('Нет Elo на момент матча');
  const form = panel.locator('form');
  await form.getByRole('textbox').fill('Сервер пропустил подготовку');
  await expect(form.getByRole('button', { name: /подготов/i })).toBeDisabled();
  await form.getByRole('checkbox').check();
  await form.getByRole('button', { name: /подготов/i }).click();
  await expect.poll(() => writes.length).toBe(1);
  expect(writes[0]).toMatchObject({ expected_revision: 8, reason: 'Сервер пропустил подготовку' });
  expect(writes[0].command_id).toBeTruthy();
  expect(paths).toContain('/api/v1/campaign/cycles/admin/diagnostics');
  await expect(form).toHaveCount(0);
  await page.screenshot({ path: 'test-results/campaign-admin-diagnostics.png', fullPage: true });
});

test('seasonal treasury keeps exact values and retries the same command after reload', async ({ page }) => {
  const { writes } = await mock(page, { loseFirst: true });
  await page.goto('/admin');
  await page.getByRole('tab', { name: 'Кланы', exact: true }).click();
  await page.getByRole('row').filter({ hasText: 'Akatsuki' }).getByRole('button', { name: /казн|эконом|измен|редакт/i }).first().click();
  let dialog = page.getByRole('dialog');
  await expect(dialog.getByRole('textbox', { name: 'Золото', exact: true })).toHaveValue('1234.123456789012');
  await expect(dialog.getByRole('textbox', { name: 'Влияние', exact: true })).toHaveCount(0);
  await dialog.getByRole('textbox', { name: /Причина/ }).fill('Ручная корректировка');
  await dialog.getByRole('button', { name: 'Сохранить', exact: true }).click();
  await expect.poll(() => writes.length).toBe(1);
  await expect(dialog.getByRole('alert').last()).toBeVisible();
  await page.reload();
  await page.getByRole('tab', { name: 'Кланы', exact: true }).click();
  await page.getByRole('row').filter({ hasText: 'Akatsuki' }).getByRole('button', { name: /казн|эконом|измен|редакт/i }).first().click();
  dialog = page.getByRole('dialog');
  await dialog.getByRole('button', { name: /Повтор/ }).click();
  await expect.poll(() => writes.length).toBe(2);
  expect(writes[1]).toEqual(writes[0]);
  await expect(dialog).toHaveCount(0);
});
