import { test, expect } from '@playwright/test';

const user = { id: 1, username: 'Head', language: 'ru', is_verified: true, is_claimed: true,
  role: { name: 'user' }, onboarding_completed: true };
const context = () => ({ cycle_id: 1, clan_id: 7, clan_name: 'Akatsuki', ready: true, can_command: true,
  phase: 'battle', server_time: '2026-10-17T12:00:00Z', command_deadline: '2026-10-18T12:00:00Z',
  players: [{ user_id: 2, name: 'Renamed reserve', available: true }, { user_id: 3, name: 'Voivode', available: true }],
  own_targets: [{ territory_id: 10, battle_id: 50 }], help_targets: [10],
  origins: [], route_previews: [],
  allied_targets: [{ request_id: 'ally-q', recipient_clan_id: 8, territory_id: 20, battle_id: 51 }],
  clans: [{ id: 7, name: 'Akatsuki' }, { id: 8, name: 'Allied clan' }],
  territories: [{ id: 10, name: 'Home' }, { id: 20, name: 'Evendim' }],
  names: [{ user_id: 2, name: 'Renamed reserve' }, { user_id: 3, name: 'Voivode' }],
  state: { revision: 1, reserves: [{ clan_id: 7, capacity: 2, player_user_ids: [2, 3] }],
    requests: [{ id: 'ally-q', recipient_clan_id: 8, territory_id: 20, dispatch_id: null }], dispatches: [], ambushes: [] } });

async function mock(page, data, options = {}) {
  const commands = [];
  await page.addInitScript(() => localStorage.setItem('language', 'ru'));
  await page.route('**/api/v1/**', route => {
    const request = route.request(), path = new URL(request.url()).pathname;
    let payload = {};
    if (path.endsWith('/auth/session') || path.endsWith('/users/me')) payload = user;
    else if (path.endsWith('/clans/my')) payload = { id: 7, name: 'Akatsuki', leader_id: 1 };
    else if (path.endsWith('/reinforcements/context')) payload = data;
    else if (request.method() === 'POST' && path.includes('/reinforcements/')) {
      const command = request.postDataJSON(); commands.push(command);
      if (options.conflict) return route.fulfill({ status: 409, json: { detail: 'Revision changed' } });
      if (options.failFirst && commands.length === 1) return route.fulfill({ status: 503, json: { detail: 'Unavailable' } });
      data.state.revision += 1;
      if (path.endsWith('/requests')) {
        data.help_targets = [];
        data.state.requests.push({ id: command.request_id, recipient_clan_id: 7, territory_id: command.territory_id, dispatch_id: null });
      } else {
        data.state.dispatches.push({ id: command.dispatch_id, sender_clan_id: 7, recipient_clan_id: command.recipient_clan_id,
          territory_id: command.territory_id, player_user_ids: command.player_user_ids,
          route: data.route_previews.find(r => r.origin_territory_id === command.origin_territory_id && r.target_territory_id === command.territory_id) || null,
          sent_at: data.server_time, arrives_at: '2026-10-18T12:00:00Z', outcome: 'clear' });
        for (const player of data.players) if (command.player_user_ids.includes(player.user_id)) {
          player.available = false; player.unavailable_reason = 'already_sent';
        }
        if (command.request_id) data.allied_targets = [];
      }
      payload = data.state;
    } else if (path.includes('notifications')) payload = { items: [], unread_count: 0, total: 0 };
    else if (path.includes('presence')) payload = { items: [] };
    else if (path.includes('localization')) payload = [];
    return route.fulfill({ json: payload });
  });
  return commands;
}

for (const width of [390, 1440]) {
  test(`allied dispatch confirms stable ids and shows arrival at ${width}px`, async ({ page }) => {
    await page.setViewportSize({ width, height: 1000 });
    const writes = await mock(page, context());
    const errors = []; page.on('pageerror', error => errors.push(error.message));
    await page.goto('/campaign/cycles/1/reinforcements');
    await page.getByRole('combobox', { name: 'Куда отправить' }).selectOption('8:20:ally-q');
    await page.getByRole('checkbox', { name: 'Renamed reserve', exact: true }).check();
    await page.getByRole('button', { name: 'Отправить подкрепление', exact: true }).click();
    await expect(page.getByRole('dialog')).toContainText('24');
    await page.getByRole('dialog').getByRole('button', { name: 'Отправить', exact: true }).click();
    await expect(page.locator('.cr-dispatch')).toContainText('Renamed reserve');
    await expect(page.locator('.cr-dispatch')).toContainText('Evendim');
    await expect(page.locator('.cr-dispatch')).toContainText('В пути');
    expect(writes).toHaveLength(1);
    expect(writes[0]).toMatchObject({ player_user_ids: [2], recipient_clan_id: 8, territory_id: 20, request_id: 'ally-q', expected_revision: 1 });
    await expect(page.getByRole('checkbox', { name: 'Renamed reserve', exact: true })).toBeDisabled();
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    expect(errors).toEqual([]);
    await page.evaluate(() => window.scrollTo({ top: 0, behavior: 'instant' }));
    await page.screenshot({ path: `test-results/cycle-reinforcements-${width}.png`, fullPage: true });
  });
}

test('own reserves and help requests use distinct commands', async ({ page }) => {
  const writes = await mock(page, context());
  await page.goto('/campaign/cycles/1/reinforcements');
  await page.getByRole('button', { name: 'Запросить помощь союзников', exact: true }).click();
  await expect(page.getByRole('status')).toContainText('Запрос отправлен');
  expect(writes[0]).toMatchObject({ territory_id: 10, expected_revision: 1 });
  expect(writes[0].request_id).toBeTruthy();
  await expect(page.getByRole('button', { name: 'Запросить помощь союзников', exact: true })).toBeDisabled();
  await page.getByRole('combobox', { name: 'Куда отправить' }).selectOption('7:10:');
  await page.getByRole('checkbox', { name: 'Voivode', exact: true }).check();
  await page.getByRole('button', { name: 'Отправить подкрепление', exact: true }).click();
  await page.getByRole('dialog').getByRole('button', { name: 'Отправить', exact: true }).click();
  await expect(page.locator('.cr-dispatch')).toBeVisible();
  expect(writes[1]).toMatchObject({ recipient_clan_id: 7, request_id: null, player_user_ids: [3], expected_revision: 2 });
});

test('a triggered interception opens its own battle from reinforcement movement', async ({ page }) => {
  const data = context();
  data.server_time = '2026-10-17T15:00:00Z';
  data.state.dispatches = [{ id: 'route-1', sender_clan_id: 7, recipient_clan_id: 7, territory_id: 10,
    player_user_ids: [2], sent_at: '2026-10-17T12:00:00Z', arrives_at: '2026-10-18T12:00:00Z',
    interception_at: '2026-10-17T14:00:00Z', interception_ends_at: '2026-10-18T02:00:00Z', outcome: 'pending' }];
  await mock(page, data);
  await page.goto('/campaign/cycles/1/reinforcements');
  await expect(page.getByRole('link', { name: 'Открыть перехват', exact: true })).toHaveAttribute('href', '/campaign/cycles/1/interception?dispatch=route-1');
});

test('ordinary member cannot request or send and sees no command forms', async ({ page }) => {
  await mock(page, { ...context(), can_command: false });
  await page.goto('/campaign/cycles/1/reinforcements');
  await expect(page.getByRole('heading', { name: 'Подкрепления и помощь' })).toBeVisible();
  await expect(page.getByRole('button', { name: 'Отправить подкрепление' })).toHaveCount(0);
  await expect(page.getByRole('button', { name: 'Запросить помощь союзников' })).toHaveCount(0);
});

test('failed send retries the same command rather than duplicating the dispatch', async ({ page }) => {
  const writes = await mock(page, context(), { failFirst: true });
  await page.goto('/campaign/cycles/1/reinforcements');
  await page.getByRole('combobox', { name: 'Куда отправить' }).selectOption('7:10:');
  await page.getByRole('checkbox', { name: 'Voivode', exact: true }).check();
  for (let attempt = 0; attempt < 2; attempt++) {
    await page.getByRole('button', { name: 'Отправить подкрепление', exact: true }).click();
    await page.getByRole('dialog').getByRole('button', { name: 'Отправить', exact: true }).click();
    if (!attempt) await expect(page.getByRole('alert')).toBeVisible();
  }
  await expect(page.locator('.cr-dispatch')).toHaveCount(1);
  expect(writes[0].dispatch_id).toBe(writes[1].dispatch_id);
});

test('background revision invalidates confirmation without clearing the selected squad', async ({ page }) => {
  await page.clock.install();
  const data = context();
  const writes = await mock(page, data);
  await page.goto('/campaign/cycles/1/reinforcements');
  await page.getByRole('combobox', { name: 'Куда отправить' }).selectOption('7:10:');
  await page.getByRole('checkbox', { name: 'Voivode', exact: true }).check();
  await page.getByRole('button', { name: 'Отправить подкрепление', exact: true }).click();
  await expect(page.getByRole('dialog')).toBeVisible();
  data.state.revision = 2;
  await page.clock.fastForward(15_000);
  await expect(page.getByRole('dialog')).toHaveCount(0);
  await expect(page.getByRole('alert')).toContainText('Данные изменились');
  await expect(page.getByRole('checkbox', { name: 'Voivode', exact: true })).toBeChecked();
  await page.getByRole('button', { name: 'Отправить подкрепление', exact: true }).click();
  await page.getByRole('dialog').getByRole('button', { name: 'Отправить', exact: true }).click();
  await expect(page.locator('.cr-dispatch')).toBeVisible();
  expect(writes[0].expected_revision).toBe(2);
});

test('closed allied request cannot be confirmed using the old target', async ({ page }) => {
  await page.clock.install();
  const data = context();
  const writes = await mock(page, data);
  await page.goto('/campaign/cycles/1/reinforcements');
  await page.getByRole('combobox', { name: 'Куда отправить' }).selectOption('8:20:ally-q');
  await page.getByRole('checkbox', { name: 'Voivode', exact: true }).check();
  await page.getByRole('button', { name: 'Отправить подкрепление', exact: true }).click();
  data.state.revision = 2; data.allied_targets = [];
  await page.clock.fastForward(15_000);
  await expect(page.getByRole('dialog')).toHaveCount(0);
  await expect(page.getByRole('button', { name: 'Отправить подкрепление', exact: true })).toBeDisabled();
  expect(writes).toEqual([]);
});

test('deadline closes confirmation and blocks sending without a poll', async ({ page }) => {
  await page.clock.install();
  const data = context(); data.command_deadline = '2026-10-17T12:00:05Z';
  const writes = await mock(page, data);
  await page.goto('/campaign/cycles/1/reinforcements');
  await page.getByRole('combobox', { name: 'Куда отправить' }).selectOption('7:10:');
  await page.getByRole('checkbox', { name: 'Voivode', exact: true }).check();
  await page.getByRole('button', { name: 'Отправить подкрепление', exact: true }).click();
  await expect(page.getByRole('dialog')).toBeVisible();
  await page.clock.fastForward(6000);
  await expect(page.getByRole('dialog')).toHaveCount(0);
  await expect(page.getByRole('button', { name: 'Отправить подкрепление', exact: true })).toBeDisabled();
  expect(writes).toEqual([]);
});

test('lost membership clears private reserve and movement data', async ({ page }) => {
  await page.clock.install();
  await mock(page, context());
  await page.goto('/campaign/cycles/1/reinforcements');
  await expect(page.getByRole('checkbox', { name: 'Voivode', exact: true })).toBeVisible();
  await page.route('**/reinforcements/context', route => route.fulfill({ status: 403, json: { detail: 'Membership required' } }));
  await page.clock.fastForward(15_000);
  await expect(page.getByRole('alert')).toBeVisible();
  await expect(page.getByRole('checkbox')).toHaveCount(0);
});

test('lost success response is reconciled from command receipt on refresh', async ({ page }) => {
  await page.clock.install();
  const data = context();
  await mock(page, data);
  await page.route('**/reinforcements/dispatches', route => {
    const command = route.request().postDataJSON();
    data.state.revision += 1;
    data.state.dispatches.push({ id: command.dispatch_id, sender_clan_id: 7, recipient_clan_id: 7, territory_id: 10,
      player_user_ids: command.player_user_ids, sent_at: data.server_time, arrives_at: '2026-10-18T12:00:00Z', outcome: 'clear' });
    data.players[1].available = false; data.players[1].unavailable_reason = 'already_sent';
    return route.fulfill({ status: 503, json: { detail: 'Response lost after commit' } });
  });
  await page.goto('/campaign/cycles/1/reinforcements');
  await page.getByRole('combobox', { name: 'Куда отправить' }).selectOption('7:10:');
  await page.getByRole('checkbox', { name: 'Voivode', exact: true }).check();
  await page.getByRole('button', { name: 'Отправить подкрепление', exact: true }).click();
  await page.getByRole('dialog').getByRole('button', { name: 'Отправить', exact: true }).click();
  await expect(page.getByRole('alert')).toBeVisible();
  await page.clock.fastForward(15_000);
  await expect(page.getByRole('status')).toContainText('Подкрепление отправлено');
  await expect(page.locator('.cr-dispatch')).toHaveCount(1);
  await expect(page.getByRole('checkbox', { name: 'Voivode', exact: true })).not.toBeChecked();
});

test('successful null clan response clears the former clan and displays the clanless state', async ({ page }) => {
  await page.clock.install();
  await mock(page, context());
  await page.goto('/campaign/cycles/1/reinforcements');
  await page.getByRole('checkbox', { name: 'Voivode', exact: true }).check();
  await page.route('**/clans/my', route => route.fulfill({ json: null }));
  await page.clock.fastForward(15_000);
  await expect(page.getByText('Для просмотра подкреплений нужно состоять в клане.', { exact: true })).toBeVisible();
  await expect(page.getByRole('checkbox')).toHaveCount(0);
  await expect(page.getByRole('heading', { name: 'Akatsuki' })).toHaveCount(0);
});

test('query-only navigation replaces the old target and discards its confirmation', async ({ page }) => {
  await mock(page, context());
  await page.goto('/campaign/cycles/1/reinforcements?territory=10');
  const target = page.getByRole('combobox', { name: 'Куда отправить' });
  await expect(target).toHaveValue('7:10:');
  await page.getByRole('checkbox', { name: 'Voivode', exact: true }).check();
  await page.getByRole('button', { name: 'Отправить подкрепление', exact: true }).click();
  await page.getByRole('button', { name: 'Отмена', exact: true }).click();
  await page.evaluate(() => {
    history.pushState({}, '', '/campaign/cycles/1/reinforcements?territory=20&recipient=8&request=ally-q');
    dispatchEvent(new PopStateEvent('popstate'));
  });
  await expect(target).toHaveValue('8:20:ally-q');
  await expect(page.getByRole('checkbox', { name: 'Voivode', exact: true })).not.toBeChecked();
});

function geographicContext() {
  const data = context();
  data.origins = [{ territory_id: 1, name: 'Арнор' }, { territory_id: 2, name: 'Форност' }];
  const nodes = [{ territory_id: 1, name: 'Арнор', svg_path_data: 'M0 0h10v10h-10z' },
    { territory_id: 2, name: 'Форност', svg_path_data: 'M10 10h10v10h-10z' },
    { territory_id: 10, name: 'Home', svg_path_data: 'M20 0h10v10h-10z' }];
  data.route_previews = data.origins.map(origin => ({ status: 'mapped', origin_territory_id: origin.territory_id,
    target_territory_id: 10, territory_ids: origin.territory_id === 1 ? [1, 2, 10] : [2, 10],
    nodes: origin.territory_id === 1 ? nodes : nodes.slice(1) }));
  return data;
}

for (const width of [390, 1440]) {
  test(`географический маршрут включает промежуточную землю при ${width}px`, async ({ page }, testInfo) => {
    await page.setViewportSize({ width, height: 1000 });
    const writes = await mock(page, geographicContext());
    await page.goto('/campaign/cycles/1/reinforcements');
    await page.getByRole('combobox', { name: 'Куда отправить' }).selectOption('7:10:');
    await page.getByRole('checkbox', { name: 'Voivode', exact: true }).check();
    await expect(page.getByRole('button', { name: 'Отправить подкрепление', exact: true })).toBeDisabled();
    await page.getByRole('combobox', { name: 'Земля отправления', exact: true }).selectOption('1');
    const preview = page.locator('form .cycle-dispatch-route');
    await expect(preview.locator('.cycle-route-line')).toHaveAttribute('points', '5,5 15,15 25,5');
    await expect(preview.getByRole('list')).toContainText('Форност');
    await page.getByRole('button', { name: 'Отправить подкрепление', exact: true }).click();
    await expect(page.getByRole('dialog')).toContainText('Земля отправления: Арнор');
    await page.getByRole('dialog').getByRole('button', { name: 'Отправить', exact: true }).click();
    await expect(page.locator('.cr-dispatch .cycle-route-line')).toHaveAttribute('points', '5,5 15,15 25,5');
    expect(writes[0]).toMatchObject({ origin_territory_id: 1, territory_id: 10 });
    await expect(page.locator('.cr-countdown')).toBeVisible();
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    await page.locator('.cr-dispatch .cycle-dispatch-route').screenshot({ path: testInfo.outputPath('geographic-route.png') });
  });
}

test('смена земли после неудачи создаёт новый ключ отправки', async ({ page }) => {
  const writes = await mock(page, geographicContext(), { failFirst: true });
  await page.goto('/campaign/cycles/1/reinforcements');
  await page.getByRole('combobox', { name: 'Куда отправить' }).selectOption('7:10:');
  await page.getByRole('checkbox', { name: 'Voivode', exact: true }).check();
  for (const origin of ['1', '2']) {
    await page.getByRole('combobox', { name: 'Земля отправления', exact: true }).selectOption(origin);
    await page.getByRole('button', { name: 'Отправить подкрепление', exact: true }).click();
    await page.getByRole('dialog').getByRole('button', { name: 'Отправить', exact: true }).click();
    if (origin === '1') await expect(page.getByRole('alert')).toBeVisible();
  }
  await expect(page.locator('.cr-dispatch')).toHaveCount(1);
  expect(writes.map(w => w.origin_territory_id)).toEqual([1, 2]);
  expect(writes[0].dispatch_id).not.toBe(writes[1].dispatch_id);
});

for (const status of ['no_origin', 'unreachable']) {
  test(`без выдуманной линии: ${status}`, async ({ page }) => {
    const data = geographicContext();
    const target = data.route_previews[0].nodes.at(-1);
    if (status === 'no_origin') data.origins = [];
    data.route_previews = [{ status, origin_territory_id: status === 'no_origin' ? null : 1,
      target_territory_id: 10, territory_ids: [], nodes: [target] }];
    const writes = await mock(page, data);
    await page.goto('/campaign/cycles/1/reinforcements');
    await page.getByRole('combobox', { name: 'Куда отправить' }).selectOption('7:10:');
    if (status === 'no_origin') await expect(page.getByRole('combobox', { name: 'Земля отправления', exact: true })).toHaveCount(0);
    else await page.getByRole('combobox', { name: 'Земля отправления', exact: true }).selectOption('1');
    await page.getByRole('checkbox', { name: 'Voivode', exact: true }).check();
    await expect(page.locator('form .cycle-route-target')).toHaveCount(1);
    await expect(page.locator('form .cycle-route-line')).toHaveCount(0);
    await page.getByRole('button', { name: 'Отправить подкрепление', exact: true }).click();
    await page.getByRole('dialog').getByRole('button', { name: 'Отправить', exact: true }).click();
    await expect(page.locator('.cr-dispatch .cycle-route-line')).toHaveCount(0);
    expect(writes[0].origin_territory_id).toBe(status === 'no_origin' ? null : 1);
  });
}

test('утрата земли отправления закрывает подтверждение без потери состава', async ({ page }) => {
  await page.clock.install();
  const data = geographicContext();
  const writes = await mock(page, data);
  await page.goto('/campaign/cycles/1/reinforcements');
  await page.getByRole('combobox', { name: 'Куда отправить' }).selectOption('7:10:');
  await page.getByRole('combobox', { name: 'Земля отправления', exact: true }).selectOption('1');
  await page.getByRole('checkbox', { name: 'Voivode', exact: true }).check();
  await page.getByRole('button', { name: 'Отправить подкрепление', exact: true }).click();
  await expect(page.getByRole('dialog')).toBeVisible();
  data.origins = data.origins.slice(1);
  await page.clock.fastForward(15_000);
  await expect(page.getByRole('dialog')).toHaveCount(0);
  await expect(page.getByRole('combobox', { name: 'Земля отправления', exact: true })).toHaveValue('');
  await expect(page.getByRole('checkbox', { name: 'Voivode', exact: true })).toBeChecked();
  expect(writes).toEqual([]);
});
