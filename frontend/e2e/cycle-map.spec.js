import { expect, test } from '@playwright/test';

const user = { id: 1, username: 'Глава', language: 'ru', is_verified: true,
  is_claimed: true, role: { name: 'user' }, onboarding_completed: true };
const territories = [
  { id: 3, name: 'Арнор', owner_clan_id: 7, status: 'contested', is_playable: true, adjacent_territory_ids: [4] },
  { id: 4, name: 'Форност', owner_clan_id: 8, status: 'contested', is_playable: true, adjacent_territory_ids: [3] },
];
const sides = [
  { clan_id: 7, clan_name: 'Защитники', score: '125.5', role: 'defense', members: [] },
  { clan_id: 8, clan_name: 'Союзники', score: '42', role: 'attack', members: [] },
];
const territoryBattle = { id: 50, cycle_id: 1, territory_id: 3, territory_name: 'Арнор', sides,
  completed_at: null, winner_clan_id: null, recalculated_winner_clan_id: null, contributions: [], adjustments: [] };
const mapData = (overrides = {}) => ({
  cycle_id: 1, clan_id: 7, phase: 'battle', ready: true, can_command: true, revision: 9,
  server_time: '2026-10-17T15:00:00Z', command_deadline: '2026-10-18T12:00:00Z',
  battles: [{ battle_id: 50, territory_id: 3, sides }, { battle_id: 51, territory_id: 4, sides }],
  help_targets: [3, 4], allied_targets: [{ request_id: 'запрос & союз', recipient_clan_id: 8, territory_id: 3 }],
  requests: [], ambushes: [], dispatches: [], territories: [{ territory_id: 3,
    profile_material: 'iron', daily_income: { gold: '265', iron: '6', wood: '0', food: '0', mithril: '0' },
    levels: { gold: 2, profile: 1, fortification: 3, offense: 1, naval: 0 }, max_level: 3 }], ...overrides,
});
const movement = (overrides = {}) => ({
  id: 'отряд & 1', sender_clan_id: 8, recipient_clan_id: 7, territory_id: 3, player_user_ids: [2],
  sent_at: '2026-10-17T12:00:00Z', arrives_at: '2026-10-18T12:00:00Z',
  interception_at: '2026-10-17T14:00:00Z', interception_ends_at: '2026-10-18T02:00:00Z', outcome: 'pending',
  ...overrides,
});

test('карта объясняет стороны, направление атаки и просьбу союзника', async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 1000 });
  await isolateApi(page, () => mapData({
    battles: [{ battle_id: 50, territory_id: 3, territory_name: 'Арнор', owner_clan_id: 7,
      owner_clan_name: 'Защитники', status: 'contested', sides }],
    attack_routes: [{ clan_id: 8, clan_name: 'Союзники', source_territory_id: 4,
      target_territory_id: 3, route: 'land', player_count: 2 }],
    requests: [{ id: 'help-1', recipient_clan_id: 8, clan_name: 'Союзники', territory_id: 3 }],
  }));
  await page.goto('/map');
  await selectTerritory(page, 'Арнор');
  const panel = page.locator('.cycle-map-panel');
  await expect(panel).toContainText('Владелец');
  await expect(panel).toContainText('Битва за территорию');
  await expect(panel.locator('.cycle-map-role')).toHaveText(['Оборона', 'Атака']);
  await expect(panel).toContainText('Нужна помощь');
  await expect(page.locator('#cycle-map-layer .cycle-map-attack')).toHaveCount(1);
  await expect(page.locator('#cycle-map-layer .cycle-map-help')).toHaveCount(1);
  await page.screenshot({ path: 'test-results/map-battle-clarity.png', fullPage: true });
});

// Все API перехватываются до открытия страницы; неизвестные запросы не доходят до прокси.
async function isolateApi(page, readMap = () => mapData(), readCycle = () => ({ id: 1 })) {
  const errors = [];
  page.on('pageerror', error => errors.push(error.message));
  await page.addInitScript(() => localStorage.setItem('language', 'ru'));
  await page.route('**/api/**', async route => {
    const path = new URL(route.request().url()).pathname;
    let json = {};
    if (path.endsWith('/auth/session') || path.endsWith('/users/me')) json = user;
    else if (path === '/api/v1/campaign/cycles/current') json = {
      mechanics_version: 'cycle_v1', cycle: readCycle(), territory_battles: [{ battle_id: 50, territory_id: 3 }],
    };
    else if (/\/campaign\/cycles\/\d+\/map$/.test(path)) json = readMap();
    else if (path.endsWith('/reinforcements/context')) {
      const map = readMap();
      json = { cycle_id: map.cycle_id, clan_id: map.clan_id, ready: map.ready, can_command: map.can_command,
        phase: map.phase, server_time: map.server_time, command_deadline: map.command_deadline,
        own_targets: map.battles.filter(b => b.sides.some(s => s.clan_id === map.clan_id))
          .map(b => ({ territory_id: b.territory_id, battle_id: b.battle_id })),
        allied_targets: map.allied_targets, help_targets: map.help_targets,
        players: [{ user_id: 2, name: 'Резервист', available: true }],
        state: { revision: map.revision, reserves: [], requests: [], dispatches: [], ambushes: [] },
        territories, clans: [], names: [], origins: [], route_previews: [] };
    }
    else if (path === '/api/v1/territories/') json = territories;
    else if (path === '/api/v1/clans/') json = [{ id: 7, name: 'Защитники' }, { id: 8, name: 'Союзники' }];
    else if (path.endsWith('/clans/my')) json = { id: 7, name: 'Защитники', leader_id: 1 };
    else if (path.endsWith('/wars/active/')) json = [{ id: 99, territory_id: 3, status: 'active', clan_scores: [] }];
    else if (path === '/api/v1/campaign/cycles/1') json = { id: 1, number: 1, phase: 'battle' };
    else if (path === '/api/v1/campaign/cycles/1/battles') json = { battles: [territoryBattle] };
    else if (path === '/api/v1/campaign/cycles/battles/50') json = territoryBattle;
    else if (path.includes('notifications')) json = { items: [], unread_count: 0, total: 0 };
    else if (path.includes('presence')) json = { items: [] };
    else if (path.includes('localization') || path.includes('diplomacy')) json = [];
    return route.fulfill({ json });
  });
  return errors;
}

for (const width of [390, 1440]) {
  test(`расписание над картой обновляет этап и дату нового цикла при ${width}px`, async ({ page }) => {
    await page.setViewportSize({ width, height: 950 });
    await page.clock.install();
    const cycle = { id: 1, number: 2, phase: 'preparation',
      preparation_at: '2026-11-12T06:40:32Z', battle_at: '2026-11-13T06:40:32Z',
      battle_ends_at: '2026-11-15T06:40:32Z' };
    await isolateApi(page, () => mapData(), () => cycle);
    await page.goto('/map');
    const ribbon = page.getByRole('region', { name: 'Расписание кампании' });
    await expect(ribbon).toContainText('Цикл 2');
    await expect(ribbon).toContainText('12.11.2026, 09:40 МСК');
    await expect(ribbon).toContainText('13.11.2026, 09:40 МСК');
    await expect(ribbon.getByRole('link', { name: 'К битвам' })).toHaveAttribute('href', '/campaign/cycles/1');
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    await page.screenshot({ path: test.info().outputPath('map-schedule.png') });
    Object.assign(cycle, { phase: 'rest', next_cycle_starts_at: '2026-11-15T19:00:00Z' });
    await page.clock.fastForward(61_000);
    await expect(ribbon).toContainText('Начало цикла 3');
    await expect(ribbon).toContainText('15.11.2026, 22:00 МСК');
    await expect(ribbon).not.toContainText('12.11.2026');
  });
}

async function selectTerritory(page, name) {
  const territory = page.getByRole('button', { name, exact: true });
  await expect(territory).toHaveAttribute('tabindex', '0');
  await territory.press('Enter');
  await expect(page.locator('.cycle-map-panel')).toBeVisible();
}

for (const width of [390, 1440]) {
  test(`карта cycle_v1 открывает битву территории и показывает помощь и перехват при ${width}px`, async ({ page }) => {
    await page.setViewportSize({ width, height: 900 });
    const errors = await isolateApi(page, () => mapData({ dispatches: [movement()],
      ambushes: [{ id: 'засада', territory_id: 3, dispatch_id: 'отряд & 1' }] }));
    await page.goto('/map');
    await selectTerritory(page, 'Арнор');
    const panel = page.locator('.cycle-map-panel');
    await expect(page.locator('.territory-summary')).not.toContainText('/10');
    await expect(page.locator('.territory-summary')).not.toContainText('48 ч.');
    await expect(page.locator('.territory-summary')).toContainText('265');
    await expect(page.locator('.territory-summary')).toContainText('3/3');
    await expect(panel.locator('.cycle-map-scores')).toContainText('Защитники');
    await expect(panel.locator('.cycle-map-scores')).toContainText('125.5');
    await expect(panel.getByRole('button', { name: 'Запросить помощь союзников' })).toBeEnabled();
    await expect(panel.getByRole('button', { name: 'Запросы союзников Союзники' })).toBeEnabled();
    const interception = panel.getByRole('link', { name: 'Открыть перехват' });
    await expect(interception).toBeVisible();
    expect(new URL(await interception.getAttribute('href'), page.url()).searchParams.get('dispatch')).toBe('отряд & 1');
    await expect(page.locator('#cycle-map-layer .cycle-map-marker')).toHaveCount(2);
    await expect(page.locator('#cycle-map-layer .cycle-map-interception')).toHaveCount(1);
    await expect(page.locator('#cycle-map-layer .cycle-map-movement')).toContainText('+1');
    await expect(page.locator('#cycle-map-layer .cycle-map-movement title')).toHaveText('Отряды в пути');
    await expect(page.getByRole('link', { name: 'Перейти к битве #99' })).toHaveCount(0);
    const battle = page.getByRole('link', { name: 'Перейти к битве #50' });
    await expect(battle).toHaveAttribute('href', '/campaign/cycles/1?territory=3');
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    await page.screenshot({ path: test.info().outputPath(`cycle-map-${width}.png`), fullPage: true });
    await battle.click();
    await expect(page).toHaveURL(/\/campaign\/cycles\/1\?territory=3$/);
    await expect(page.locator('.cycle-detail')).toBeVisible();
    await expect(page.getByRole('heading', { name: 'Арнор', exact: true })).toBeVisible();
    expect(errors).toEqual([]);
  });
}

test('обычный участник не запрашивает помощь и не видит ещё не начавшийся перехват', async ({ page }) => {
  await isolateApi(page, () => mapData({ can_command: false,
    dispatches: [movement({ interception_at: '2026-10-17T16:00:00Z', outcome: 'clear' })] }));
  await page.goto('/map');
  await selectTerritory(page, 'Арнор');
  const panel = page.locator('.cycle-map-panel');
  await expect(panel).toContainText('В пути');
  await expect(panel.getByRole('button', { name: 'Запросить помощь союзников' })).toHaveCount(0);
  await expect(panel.getByRole('link', { name: 'Открыть перехват' })).toHaveCount(0);
  await expect(panel.getByRole('button', { name: 'Отправить подкрепление', exact: true })).toHaveCount(0);
});

// Стенд загружает настоящие компонент и хук через Vite без изменений кода приложения.
async function openPanel(page, keyed = false) {
  const errors = [];
  page.on('pageerror', error => errors.push(error.message));
  const source = await (await page.request.get('/src/components/map/CycleMap.jsx')).text();
  const routerUrl = source.match(/from ["']([^"']*react-router-dom\.js[^"']*)["']/)?.[1];
  expect(routerUrl, 'Стенд использует тот же экземпляр роутера, что и компонент').toBeTruthy();
  await page.route('**/__cycle-map-panel', route => route.fulfill({ contentType: 'text/html', body: `
    <html lang="ru"><head><meta charset="utf-8"></head><body><div id="root"></div><script type="module">
      import RefreshRuntime from '/@react-refresh';
      RefreshRuntime.injectIntoGlobalHook(window);
      window.$RefreshReg$ = () => {}; window.$RefreshSig$ = () => type => type;
      window.__vite_plugin_react_preamble_installed__ = true;
      const { default: React } = await import('/node_modules/.vite/deps/react.js');
      const { useState } = React;
      const { default: ReactDOM } = await import('/node_modules/.vite/deps/react-dom_client.js');
      const { BrowserRouter } = await import(${JSON.stringify(routerUrl)});
      const { CycleMapPanel } = await import('/src/components/map/CycleMap.jsx');
      const { default: useCycleMap } = await import('/src/hooks/useCycleMap.js');
      const h = React.createElement;
      function Stand() {
        const [cycleId, setCycle] = useState(1), [userId, setUser] = useState(1);
        const [territoryId, setTerritory] = useState(3), [refreshes, setRefreshes] = useState(0);
        const map = useCycleMap(cycleId, userId);
        return h(BrowserRouter, null,
          h('button', { onClick: () => setTerritory(4) }, 'Другая территория'),
          h('button', { onClick: () => setCycle(2) }, 'Другой цикл'),
          h('button', { onClick: () => setUser(2) }, 'Другой пользователь'),
          h('button', { onClick: map.refresh }, 'Обновить карту'),
          h('output', { 'aria-label': 'Обновления после команды' }, refreshes),
          h('output', { 'aria-label': 'Клан карты' }, map.data?.clan_id ?? 'нет'),
          h(CycleMapPanel, { ...map, territoryId, cycleId, language: 'ru',
            key: ${keyed ? '`${cycleId}:${territoryId}:${map.data?.clan_id}`' : "'панель'"},
            refresh: () => { setRefreshes(n => n + 1); map.refresh(); } }));
      }
      ReactDOM.createRoot(document.getElementById('root')).render(h(Stand));
    </script></body></html>` }));
  await page.goto('/__cycle-map-panel');
  await expect.poll(async () => errors.length || await page.getByRole('button', { name: 'Обновить карту' }).count()).toBeTruthy();
  expect(errors).toEqual([]);
}

async function pendingHelp(page) {
  const pending = [];
  await page.route('**/reinforcements/requests', route => { pending.push(route); });
  return pending;
}

async function finishHelp(page, route, status) {
  const response = page.waitForResponse(response => response.url() === route.request().url()
    && response.request().postData() === route.request().postData());
  await route.fulfill({ status, json: status === 200 ? { revision: 10 } : { detail: 'Данные изменились' } });
  await (await response).finished();
  await page.evaluate(() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve))));
}

for (const scope of ['территория', 'клан', 'цикл']) {
  for (const status of [200, 409]) {
    test(`поздний ответ помощи ${status} не меняет новую панель: ${scope}`, async ({ page }) => {
      let data = mapData();
      const errors = await isolateApi(page, () => data);
      const pending = await pendingHelp(page);
      await openPanel(page);
      const panel = page.locator('.cycle-map-panel');
      const help = panel.getByRole('button', { name: 'Запросить помощь союзников' });
      await help.click();
      await expect.poll(() => pending.length).toBe(1);
      if (scope === 'территория') await page.getByRole('button', { name: 'Другая территория' }).click();
      if (scope === 'клан') {
        data = mapData({ clan_id: 8 });
        await page.getByRole('button', { name: 'Обновить карту' }).click();
        await expect(page.getByLabel('Клан карты')).toHaveText('8');
      }
      if (scope === 'цикл') {
        data = mapData({ cycle_id: 2 });
        await page.getByRole('button', { name: 'Другой цикл' }).click();
        await expect(panel.getByRole('button', { name: 'Отправить подкрепление', exact: true })).toBeVisible();
      }
      await expect(help).toBeEnabled();
      await help.click();
      await expect.poll(() => pending.length).toBe(2);
      const first = pending[0].request().postDataJSON(), second = pending[1].request().postDataJSON();
      expect(first).toMatchObject({ territory_id: 3, expected_revision: 9 });
      expect(second.territory_id).toBe(scope === 'территория' ? 4 : 3);
      expect(second.request_id).not.toBe(first.request_id);
      expect(pending[1].request().url()).toContain(scope === 'клан' ? '/1/clans/8/' : scope === 'цикл' ? '/2/clans/7/' : '/1/clans/7/');
      await finishHelp(page, pending[0], status);
      await expect(help).toBeDisabled();
      await expect(panel).toHaveAttribute('aria-busy', 'true');
      await expect(panel.getByRole('status')).toHaveCount(0);
      await expect(panel.getByRole('alert')).toHaveCount(0);
      await expect(page.getByLabel('Обновления после команды')).toHaveText('0');
      await finishHelp(page, pending[1], 200);
      await expect(panel.getByRole('status')).toContainText('Запрос отправлен');
      await expect(panel).toHaveAttribute('aria-busy', 'false');
      await expect(page.getByLabel('Обновления после команды')).toHaveText('1');
      expect(errors).toEqual([]);
    });
  }
}

test('снятая с экрана панель не обновляет карту ответом старой команды', async ({ page }) => {
  await isolateApi(page);
  const pending = await pendingHelp(page);
  await openPanel(page, true);
  await page.getByRole('button', { name: 'Запросить помощь союзников' }).click();
  await expect.poll(() => pending.length).toBe(1);
  await page.getByRole('button', { name: 'Другая территория' }).click();
  await expect(page.getByRole('button', { name: 'Запросить помощь союзников' })).toBeEnabled();
  await finishHelp(page, pending[0], 200);
  await expect(page.getByLabel('Обновления после команды')).toHaveText('0');
  await expect(page.locator('.cycle-map-panel').getByRole('status')).toHaveCount(0);
});

test('повтор запроса помощи после сбоя сохраняет request_id и блокируется после успеха', async ({ page }) => {
  await isolateApi(page);
  const pending = await pendingHelp(page);
  await openPanel(page);
  const help = page.getByRole('button', { name: 'Запросить помощь союзников' });
  await help.click();
  await expect.poll(() => pending.length).toBe(1);
  await finishHelp(page, pending[0], 503);
  await expect(page.locator('.cycle-map-panel').getByRole('alert')).toBeVisible();
  await expect(help).toBeEnabled();
  await help.click();
  await expect.poll(() => pending.length).toBe(2);
  expect(pending[1].request().postDataJSON()).toEqual(pending[0].request().postDataJSON());
  await finishHelp(page, pending[1], 200);
  await expect(page.locator('.cycle-map-panel').getByRole('status')).toBeVisible();
  await expect(help).toBeDisabled();
});

for (const scope of ['цикл', 'пользователь']) {
  test(`useCycleMap отбрасывает старый GET при переключении: ${scope}`, async ({ page }) => {
    await isolateApi(page);
    const maps = [];
    await page.route('**/campaign/cycles/*/map', route => { maps.push(route); });
    await openPanel(page);
    await expect.poll(() => maps.length).toBe(1);
    await page.getByRole('button', { name: scope === 'цикл' ? 'Другой цикл' : 'Другой пользователь' }).click();
    await expect.poll(() => maps.length).toBe(2);
    await maps[1].fulfill({ json: mapData({ cycle_id: scope === 'цикл' ? 2 : 1, clan_id: 8 }) });
    await expect(page.getByLabel('Клан карты')).toHaveText('8');
    await maps[0].fulfill({ json: mapData() });
    await page.evaluate(() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve))));
    await expect(page.getByLabel('Клан карты')).toHaveText('8');
    await expect(page.getByRole('button', { name: 'Запросить помощь союзников' })).toBeEnabled();
  });
}
