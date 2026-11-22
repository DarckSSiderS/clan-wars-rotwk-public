import { test, expect } from '@playwright/test';

async function prepare(page, { arrived = false, admin = true, failOnce = false, contributions = [] } = {}) {
  const sent = [];
  const applied = { outcome: 'exhausted', help_score: '200', ambush_scores: { 8: '-100' } };
  const data = { cycle_id: 1, dispatch_id: 'd', territory_id: 10, territory_name: 'Арнор',
    revision: 1, phase: 'completed', outcome: 'exhausted',
    server_time: arrived ? '2026-10-18T00:00:00Z' : '2026-10-17T15:00:00Z',
    starts_at: '2026-10-17T02:00:00Z', ends_at: '2026-10-17T14:00:00Z',
    replay_deadline: '2026-10-17T14:05:00Z', arrives_at: '2026-10-18T00:00:00Z',
    applied_result: applied, original_applied_result: applied, adjustments: [], audit: [],
    sides: [
      { clan_id: 7, clan_name: 'Помощники', role: 'help', score: '200', members: [{ user_id: 2, display_name: 'Помощник' }] },
      { clan_id: 8, clan_name: 'Засада', role: 'ambush', score: '-100', members: [{ user_id: 3, display_name: 'Перехватчик' }] },
    ], contributions,
  };
  await page.addInitScript(() => localStorage.setItem('language', 'ru'));
  await page.route('**/api/v1/**', route => {
    const url = new URL(route.request().url());
    const path = url.pathname;
    let json = {};
    if (path.endsWith('/auth/session') || path.endsWith('/users/me')) json = {
      id: 1, username: 'Проверяющий', language: 'ru', is_verified: true,
      is_claimed: true, onboarding_completed: true, role: { name: admin ? 'admin' : 'user' },
    };
    else if (path.includes('/interception')) {
      expect(url.searchParams.get('dispatch_id')).toBe('d');
      if (route.request().method() === 'GET') json = data;
      else {
        const body = route.request().postDataJSON();
        sent.push({ path, body });
        if (failOnce) { failOnce = false; return route.fulfill({ status: 503, json: { detail: 'Временная ошибка' } }); }
        if (path.endsWith('/adjustments')) {
          data.revision += 1;
          data.adjustments = [{ id: 1, clan_id: body.side_clan_id, points: body.amount,
            reason: body.reason, created_at: data.server_time }];
          json = { revision: data.revision, adjustment_id: 1 };
        } else if (path.endsWith('/contributions')) {
          data.revision += 1;
          const row = data.contributions.find(item => item.replay_id === body.replay_id && item.user_id === body.user_id);
          row.counted = body.counted;
          json = { revision: data.revision };
        } else if (path.endsWith('/preview')) json = { revision: data.revision,
          preview_command_id: body.command_id, proposed_result: { outcome: 'blocked',
            help_score: '200', ambush_scores: { 8: '500' } } };
        else {
          data.revision += 1;
          data.outcome = 'blocked';
          data.applied_result = { outcome: 'blocked', help_score: '200', ambush_scores: { 8: '500' } };
          json = { revision: data.revision, applied_result: data.applied_result };
        }
      }
    } else if (path.includes('notifications')) json = { items: [], total: 0, unread_count: 0 };
    else if (path.includes('presence')) json = { items: [] };
    else if (path.includes('localization')) json = [];
    return route.fulfill({ json });
  });
  const errors = [];
  page.on('pageerror', e => errors.push(e.message));
  await page.goto('/campaign/cycles/1/interception?dispatch=d');
  await expect(page.locator('.ci-sides > li')).toHaveCount(2);
  return { sent, data, errors };
}

for (const width of [390, 1440]) {
  test(`Администратор меняет счёт без автоматической смены исхода при ${width}px`, async ({ page }, testInfo) => {
    await page.setViewportSize({ width, height: 1000 });
    const { sent, errors } = await prepare(page);
    const form = page.locator('.ci-admin > .ci-review-form');
    await form.getByLabel('Изменение очков').fill('125.5');
    await form.getByLabel('Причина', { exact: true }).fill('Исправление пропущенной игры');
    await expect(form.getByRole('button', { name: 'Сохранить правку', exact: true })).toBeDisabled();
    await form.getByRole('checkbox').check();
    await form.getByRole('button', { name: 'Сохранить правку', exact: true }).click();
    await expect(page.locator('.ci-adjustments')).toContainText('125.5');
    await expect(page.locator('.ci-result')).toContainText('продолжает путь');
    expect(sent).toHaveLength(1);
    expect(sent[0].body).toMatchObject({ amount: '125.5', expected_revision: 1 });
    await page.screenshot({ path: testInfo.outputPath('interception-review.png'), fullPage: true });
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1)).toBe(true);
    expect(errors).toEqual([]);
  });
}

test('Изменение судьбы требует отдельного просмотра и подтверждения', async ({ page }) => {
  const { sent } = await prepare(page);
  const panel = page.locator('.ci-outcome-review');
  await panel.getByLabel('Причина', { exact: true }).fill('Подтверждение исправленного перехвата');
  await panel.getByRole('button', { name: 'Предпросмотр изменения исхода', exact: true }).click();
  await expect(panel.getByRole('button', { name: 'Применить исход подкрепления', exact: true })).toBeDisabled();
  await expect(page.locator('.ci-result')).toContainText('продолжает путь');
  await panel.getByRole('checkbox').check();
  await panel.getByRole('button', { name: 'Применить исход подкрепления', exact: true }).click();
  await expect(page.locator('.ci-result')).toContainText('остановлено');
  expect(sent.map(r => r.path.split('/').at(-1))).toEqual(['preview', 'confirm']);
  expect(sent[1].body.preview_command_id).toBe(sent[0].body.command_id);
});

test('После прибытия доступна история, но нет применения исхода', async ({ page }) => {
  await prepare(page, { arrived: true });
  await expect(page.locator('.ci-outcome-review')).toContainText('не откатываются');
  await expect(page.getByRole('button', { name: 'Предпросмотр изменения исхода', exact: true })).toHaveCount(0);
  await expect(page.locator('.ci-admin > .ci-review-form')).toBeVisible();
});

test('Повтор поправки после сбоя отправляет прежний ключ и версию', async ({ page }) => {
  const { sent } = await prepare(page, { failOnce: true });
  const form = page.locator('.ci-admin > .ci-review-form');
  await form.getByLabel('Изменение очков').fill('25');
  await form.getByLabel('Причина', { exact: true }).fill('Пропущенные очки');
  for (let i = 0; i < 2; i += 1) {
    await form.getByRole('checkbox').check();
    await form.getByRole('button', { name: 'Сохранить правку', exact: true }).click();
    if (i === 0) await expect(form.getByRole('alert')).toBeVisible();
  }
  await expect(page.locator('.ci-adjustments')).toBeVisible();
  expect(sent[0].body).toEqual(sent[1].body);
});

test('Обычному игроку формы пересмотра не показываются', async ({ page }) => {
  const { sent } = await prepare(page, { admin: false });
  await expect(page.locator('.ci-admin')).toHaveCount(0);
  expect(sent).toEqual([]);
});

test('Polling требует нового выбора и подтверждения при смене версии или исходного вклада', async ({ page }) => {
  await page.clock.install();
  const { sent, data, errors } = await prepare(page, { contributions: [
    { replay_id: 'bfmeladder:review-1', user_id: 2, clan_id: 7, points: '200', counted: true,
      reason: 'counted', calculation: { historical_elo: '1200', base_points: '100', direct_multiplier: 2 } },
  ] });
  await page.locator('.cycle-match > summary').click();
  await page.locator('.ci-contribution-review > summary').click();
  const form = page.locator('.ci-contribution-review > .ci-review-form');
  const reason = form.getByRole('textbox', { name: 'Причина', exact: true });
  const counted = form.getByRole('checkbox', { name: 'Учитывать вклад', exact: true });
  const confirmed = form.getByRole('checkbox', { name: 'Подтверждаю исправление истории счёта без изменения исхода подкрепления', exact: true });
  const save = form.getByRole('button', { name: 'Сохранить правку', exact: true });
  const poll = async () => {
    const response = page.waitForResponse(res => res.request().method() === 'GET'
      && new URL(res.url()).pathname.endsWith('/interception/review'));
    await page.clock.fastForward(15_000);
    await response;
    await expect(page.locator('.cycle-interception')).toHaveAttribute('aria-busy', 'false');
  };

  await counted.uncheck();
  await reason.fill('Проверенное исключение матча');
  await confirmed.check();
  await expect(save).toBeEnabled();
  await poll();
  await expect(confirmed).toBeChecked();
  await expect(counted).not.toBeChecked();
  await expect(save).toBeEnabled();

  data.revision = 2;
  await poll();
  await expect(confirmed).not.toBeChecked();
  await expect(counted).toBeChecked();
  await expect(save).toBeDisabled();
  expect(sent).toHaveLength(0);

  await counted.uncheck();
  await confirmed.check();
  await expect(save).toBeEnabled();
  data.contributions[0].counted = false;
  data.revision = 3;
  await poll();
  await expect(confirmed).not.toBeChecked();
  await expect(counted).not.toBeChecked();
  await expect(save).toBeDisabled();
  expect(sent).toHaveLength(0);

  await counted.check();
  await reason.fill('Повторная проверка: восстановить вклад');
  await expect(save).toBeDisabled();
  await confirmed.check();
  await save.click();
  await expect(form.getByRole('status')).toHaveText('Правка сохранена');
  expect(sent).toHaveLength(1);
  expect(sent[0].path).toMatch(/\/interception\/review\/contributions$/);
  expect(sent[0].body).toMatchObject({ expected_revision: 3, replay_id: 'bfmeladder:review-1',
    user_id: 2, counted: true, reason: 'Повторная проверка: восстановить вклад' });
  expect(errors).toEqual([]);
});
