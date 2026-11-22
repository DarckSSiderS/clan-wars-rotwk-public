import { test, expect } from '@playwright/test';

const user = { id: 1, username: 'tester', language: 'ru', is_verified: true,
  is_claimed: true, role: { name: 'admin' }, onboarding_completed: true };
const battle = {
  id: 1, cycle_id: 1, territory_id: 2, territory_name: 'Test territory', completed_at: null,
  winner_clan_id: null, recalculated_winner_clan_id: null, adjustments: [],
  sides: [
    { clan_id: 1, clan_name: 'First clan', avatar_url: null, score: '100.125', role: 'defense', members: [{ user_id: 1, username: 'First player' }] },
    { clan_id: 2, clan_name: 'Second clan', avatar_url: null, score: '-50.25', role: 'attack', members: [{ user_id: 2, username: 'Second player' }] },
    { clan_id: 3, clan_name: 'Third clan', avatar_url: null, score: '25', role: 'attack', members: [{ user_id: 3, username: 'Third player' }] },
  ],
  contributions: [{ replay_id: 'replay-1', user_id: 1, clan_id: 1, points: '0', counted: false,
    reason: 'missing_historical_elo', review_reason: null,
    calculation: { historical_elo: null, base_points: '0', victory_bonus_percent: '0',
      direct_multiplier: 1, exhaustion_multiplier: '1' } }],
};

async function mockApi(page) {
  await page.addInitScript(() => localStorage.setItem('language', 'ru'));
  await page.route('**/api/v1/**', route => {
    const path = new URL(route.request().url()).pathname;
    let payload = {};
    if (path.endsWith('/auth/session') || path.endsWith('/users/me')) payload = user;
    else if (path === '/api/v1/campaign/cycles/1') payload = {
      id: 1, number: 1, phase: 'battle', battle_at: '2026-10-15T00:00:00Z',
      battle_ends_at: '2026-10-17T00:00:00Z', replay_deadline: '2026-10-17T00:05:00Z',
    };
    else if (path === '/api/v1/campaign/cycles/1/battles') payload = { battles: [battle] };
    else if (path === '/api/v1/campaign/cycles/diplomacy/cycles/1') payload = { relations: [
      { clan_low_id: 1, clan_high_id: 2, clan_low: { id: 1, name: 'First clan' },
        clan_high: { id: 2, name: 'Second clan' }, status: 'hostile', declarations: {}, allied_at: null },
    ] };
    else if (path === '/api/v1/campaign/cycles/battles/1') payload = battle;
    else if (path.includes('notifications')) payload = { items: [], unread_count: 0, total: 0 };
    else if (path.includes('presence')) payload = { items: [] };
    else if (path.includes('localization')) payload = [];
    else if (path.includes('clans/my')) return route.fulfill({ status: 404, json: { detail: 'No clan' } });
    return route.fulfill({ json: payload });
  });
}

test('territory feed shows actual teams, per-clan deltas and rejection without splitting a team match', async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 1000 });
  await mockApi(page);
  const detail = structuredClone(battle);
  detail.contributions = [
    { replay_id: 'bfmeladder:team', user_id: 1, clan_id: 1, points: '100.125', counted: true, reason: 'counted' },
    { replay_id: 'bfmeladder:team', user_id: 2, clan_id: 2, points: '-50.25', counted: true, reason: 'counted' },
    { replay_id: 'bfmeladder:short', user_id: 1, clan_id: 1, points: '0', counted: false, reason: 'too_short' },
  ];
  detail.matches = [
    { replay_id: 'bfmeladder:team', map_name: 'Fords of Isen', game_mode: '2 vs 2', duration: '00:20:00', played_at: '2026-10-16T12:00:00Z', participants: [
      { user_id: 1, name: 'First player', team: 1, is_winner: true }, { user_id: 7, name: 'Outside ally', team: 1, is_winner: true },
      { user_id: 2, name: 'Second player', team: 2, is_winner: false }, { user_id: 8, name: 'Outside opponent', team: 2, is_winner: false }] },
    { replay_id: 'bfmeladder:short', map_name: 'Buckland', game_mode: '1 vs 1', duration: '00:00:45', played_at: '2026-10-16T13:00:00Z', participants: [] },
  ];
  await page.route('**/api/v1/campaign/cycles/battles/1', route => route.fulfill({ json: detail }));
  await page.goto('/campaign/cycles/1?territory=2');
  await expect(page.locator('.cycle-match')).toHaveCount(2);
  const team = page.locator('.cycle-match').filter({ hasText: 'Outside ally' });
  await expect(team.locator(':scope > summary')).toContainText('Outside opponent');
  await expect(team.locator(':scope > summary')).toContainText('+100.125');
  await expect(team.locator(':scope > summary')).toContainText('-50.25');
  await expect(team.locator(':scope > summary')).toContainText('Победа');
  await expect(team.locator(':scope > summary')).toContainText('2 vs 2');
  await page.locator('.cycle-match').filter({ hasText: 'Buckland' }).locator(':scope > summary').click();
  await expect(page.locator('.cycle-contribution-reason')).toContainText('минут');
  await page.getByRole('button', { name: 'Без зачёта', exact: true }).click();
  await expect(page.locator('.cycle-match')).toHaveCount(1);
  await page.getByRole('button', { name: 'Все матчи', exact: true }).click();
  await page.screenshot({ path: 'test-results/readable-territory-matches.png', fullPage: true });
});

test('refresh on an open territory reloads its match feed as well as the scoreboard', async ({ page }) => {
  await mockApi(page);
  const detail = structuredClone(battle);
  let reads = 0;
  await page.route('**/api/v1/campaign/cycles/battles/1', route => { reads++; return route.fulfill({ json: detail }); });
  await page.goto('/campaign/cycles/1?territory=2');
  await expect(page.locator('.cycle-match')).toHaveCount(1);
  detail.contributions.push({ replay_id: 'new-match', user_id: 2, clan_id: 2, points: '100', counted: true, reason: 'counted' });
  await page.getByRole('button', { name: 'Обновить', exact: true }).click();
  await expect(page.locator('.cycle-match')).toHaveCount(2);
  expect(reads).toBeGreaterThan(1);
});

test('battle overview has campaign navigation and keeps dates out of the main content', async ({ page }) => {
  await mockApi(page);
  await page.goto('/campaign/cycles/1');
  await expect(page.locator('.cycle-navigation')).toBeVisible();
  await expect(page.locator('.cycle-clan-card')).toHaveCount(3);
  await page.screenshot({ path: 'test-results/cycle-overview-1440.png', fullPage: true });
  await expect(page.locator('.cycle-times')).toBeHidden();
  await page.getByRole('button', { name: 'Сроки цикла', exact: true }).click();
  await expect(page.locator('.cycle-times')).toBeVisible();
  await page.getByRole('button', { name: 'Территории', exact: true }).click();
  await expect(page.locator('.cycle-battle')).toHaveCount(1);
  await page.getByRole('button', { name: 'Подробности битвы', exact: true }).click();
  await expect(page).toHaveURL(/territory=2/);
  await expect(page.locator('.cycle-detail')).toBeVisible();
  await expect(page.locator('.cycle-admin-tools')).toHaveCount(0);
  await expect(page.locator('.cycle-admin')).toBeHidden();
  await page.reload();
  await expect(page.locator('.cycle-detail')).toBeVisible();
});

test('schedule moves to the current phase and shows the following cycle after settlement', async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await mockApi(page);
  await page.clock.install();
  const cycle = {
    id: 1, number: 1, phase: 'preparation',
    starts_at: '2026-11-04T17:56:53Z', preparation_at: '2026-11-07T17:56:53Z',
    battle_at: '2026-11-08T17:56:53Z', battle_ends_at: '2026-11-10T17:56:53Z',
    replay_deadline: '2026-11-10T18:01:53Z', settled_at: null, next_cycle_starts_at: null,
  };
  await page.route('**/api/v1/campaign/cycles/1', route => route.fulfill({ json: cycle }));
  await page.goto('/campaign/cycles/1');
  await page.getByRole('button', { name: 'Сроки цикла', exact: true }).click();
  const schedule = page.locator('#cycle-schedule');
  await expect(schedule.locator('[aria-current="step"]')).toContainText('Подготовка');
  await expect(schedule).not.toContainText('04.11.2026');
  await expect(schedule.locator('.cycle-schedule-next')).toContainText('После итогов и перерыва');

  Object.assign(cycle, { phase: 'rest', settled_at: '2026-11-11T18:40:32Z',
    next_cycle_starts_at: '2026-11-12T06:40:32Z' });
  await page.clock.fastForward(31_000);
  await expect(schedule.locator('[aria-current="step"]')).toContainText('Начало перерыва');
  await expect(schedule.locator('.cycle-schedule-next')).toContainText('12.11.2026, 09:40 МСК');
  await expect(schedule.locator(':scope > div')).toHaveCount(2);
  await expect(page.locator('.cycle-deadline')).toContainText('Начало цикла 2');
  await expect(page.locator('.cycle-deadline')).toContainText('12.11.2026, 09:40 МСК');
  await schedule.screenshot({ path: 'test-results/cycle-schedule-desktop.png' });
  await page.setViewportSize({ width: 390, height: 800 });
  await expect(schedule).toBeVisible();
  expect(await schedule.evaluate(el => el.scrollWidth <= el.clientWidth)).toBe(true);
  await schedule.screenshot({ path: 'test-results/cycle-schedule-mobile.png' });
});

test('clanless player can read diplomacy without a private-data error', async ({ page }) => {
  await mockApi(page);
  await page.goto('/campaign/cycles/1/diplomacy');
  await expect(page.getByRole('heading', { name: 'Дипломатия', exact: true })).toBeVisible();
  await expect(page.locator('.cd-relation')).toContainText('First clan');
  await expect(page.locator('.cd-relation')).toContainText('Second clan');
  await expect(page.locator('.cd-management')).toHaveCount(0);
  await expect(page.getByRole('alert')).toHaveCount(0);
});

test('long player name does not split a normal score on mobile', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 1000 });
  await mockApi(page);
  const detail = structuredClone(battle);
  detail.sides[0].members[0].display_name = 'Очень длинное имя игрока после смены на Арене';
  detail.contributions[0].points = '205.5';
  await page.route('**/api/v1/campaign/cycles/battles/1', route => route.fulfill({ json: detail }));
  await page.goto('/campaign/cycles/1?territory=2');
  await page.locator('.cycle-match > summary').click();
  const score = page.locator('.cycle-contribution-score strong');
  await expect(score).toHaveText('205.5');
  expect(await score.evaluate(element => element.getBoundingClientRect().height <= parseFloat(getComputedStyle(element).lineHeight) * 1.2)).toBe(true);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
});

test('an uncertain manual adjustment keeps its command when switching tabs', async ({ page }) => {
  await mockApi(page);
  const posts = [];
  await page.route('**/api/v1/campaign/cycles/battles/1/adjustments', route => {
    posts.push(route.request().postDataJSON());
    return posts.length === 1 ? route.abort('failed') : route.fulfill({ json: battle });
  });
  await page.goto('/campaign/cycles/1?territory=2');
  await page.getByRole('tab', { name: /Управление/ }).click();
  const form = page.locator('.cycle-admin-tools form.cycle-admin');
  await form.getByLabel('Изменение очков', { exact: true }).fill('25');
  await form.getByLabel('Причина', { exact: true }).fill('Повтор после потери ответа');
  await form.getByRole('button', { name: 'Сохранить', exact: true }).click();
  await expect(form.getByRole('alert')).toBeVisible();
  await page.getByRole('tab', { name: /Составы/ }).click();
  await page.getByRole('tab', { name: /Управление/ }).click();
  await expect(form.getByLabel('Изменение очков', { exact: true })).toHaveValue('25');
  await form.getByRole('button', { name: 'Сохранить', exact: true }).click();
  await expect(form.getByRole('status')).toBeVisible();
  expect(posts).toHaveLength(2);
  expect(posts[0]).toEqual(posts[1]);
});

test('imported replay opens statistics by its original Arena identifier', async ({ page }) => {
  await mockApi(page);
  const detail = structuredClone(battle);
  detail.contributions[0].replay_id = 'bfmeladder:arena-replay-1';
  await page.route('**/api/v1/campaign/cycles/battles/1', route => route.fulfill({ json: detail }));
  const seen = [];
  await page.route('**/api/v1/statistics/matches/*', route => {
    seen.push(new URL(route.request().url()).pathname);
    return route.fulfill({ json: { id: 1, match_id: 'arena-replay-1', participants: [] } });
  });
  await page.goto('/campaign/cycles/1?territory=2');
  await page.locator('.cycle-match > summary').click();
  await page.getByRole('button', { name: 'Данные матча', exact: true }).click();
  await expect(page.getByRole('dialog').first()).toBeVisible();
  await expect.poll(() => seen).toEqual(['/api/v1/statistics/matches/arena-replay-1']);
});

test('main battle entry opens the current cycle and preserves the territory link', async ({ page }) => {
  await mockApi(page);
  const legacyRequests = [];
  page.on('request', request => {
    if (new URL(request.url()).pathname.startsWith('/api/v1/wars/')) legacyRequests.push(request.url());
  });
  await page.route('**/api/v1/campaign/cycles/current', route => route.fulfill({ json: {
    mechanics_version: 'cycle_v1', cycle: { id: 1 }, territory_battles: [{ battle_id: 1, territory_id: 2 }],
  } }));
  await page.goto('/battles?territory=2');
  await expect(page).toHaveURL(/\/campaign\/cycles\/1\?territory=2$/);
  await expect(page.locator('.cycle-detail')).toBeVisible();
  await expect(page.getByRole('link', { name: 'Дипломатия', exact: true })).toHaveAttribute('href', '/campaign/cycles/1/diplomacy');
  expect(legacyRequests).toEqual([]);
});

test('missing cycle and failed lookup never load old battles', async ({ page }) => {
  await mockApi(page);
  const legacyRequests = [];
  page.on('request', request => {
    if (new URL(request.url()).pathname.startsWith('/api/v1/wars/')) legacyRequests.push(request.url());
  });
  let failed = true;
  await page.route('**/api/v1/campaign/cycles/current', route => failed
    ? route.fulfill({ status: 503, json: { detail: 'Temporary outage' } })
    : route.fulfill({ json: { mechanics_version: 'cycle_v1', cycle: null, territory_battles: [] } }));
  await page.goto('/wars');
  await expect(page.getByRole('alert')).toBeVisible();
  expect(legacyRequests).toEqual([]);
  failed = false;
  await page.getByRole('button', { name: 'Повторить', exact: true }).click();
  await expect(page.getByText('Цикл ещё не открыт', { exact: true })).toBeVisible();
  expect(legacyRequests).toEqual([]);
});

for (const width of [390, 1440]) {
  test(`cycle battle keeps all three sides visible at ${width}px`, async ({ page }) => {
    await page.setViewportSize({ width, height: 1000 });
    await mockApi(page);
    const errors = [];
    page.on('pageerror', error => errors.push(error.message));
    await page.goto('/campaign/cycles/1');
    await expect(page.locator('.cycle-clan-card')).toHaveCount(3);
    await page.screenshot({ path: `test-results/cycle-overview-${width}.png`, fullPage: true });
    await page.getByRole('button', { name: /First clan/ }).click();
    const card = page.locator('.cycle-battle');
    await expect(card).toContainText('First clan');
    await expect(card).toContainText('Second clan');
    await expect(card).toContainText('Third clan');
    await card.getByRole('button', { name: 'Подробности битвы', exact: true }).click();
    await expect(page.locator('.cycle-detail')).toBeVisible();
    await page.getByRole('tab', { name: /Составы/ }).click();
    await expect(page.locator('.cycle-lineups')).toContainText('First player');
    await page.getByRole('tab', { name: /Матчи/ }).click();
    await page.locator('.cycle-match > summary').click();
    await expect(page.locator('.cycle-contribution')).toBeVisible();
    await expect(page.locator('.cycle-contribution')).not.toContainText('missing_historical_elo');
    await page.locator('.cycle-math > summary').click();
    await expect(page.locator('.cycle-calculation')).toContainText('Elo на момент матча');
    await expect(page.locator('.cycle-calculation')).toContainText('Бонус победы');
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    expect(errors).toEqual([]);
    await page.evaluate(() => window.scrollTo(0, 0));
    await page.screenshot({ path: `test-results/cycle-battles-${width}.png`, fullPage: true });
  });
}

for (const width of [390, 1440]) {
  test(`ownership correction requires a current preview and confirmation at ${width}px`, async ({ page }) => {
    await page.setViewportSize({ width, height: 1000 });
    await mockApi(page);
    let detail = { ...battle, completed_at: '2026-10-17T00:05:00Z',
      ownership_applied_at: '2026-10-17T00:05:00Z', winner_clan_id: 2,
      recalculated_winner_clan_id: 1, current_owner_clan_id: 2, current_owner_name: 'Second clan',
      ownership_corrections: [] };
    let token = 'a'.repeat(64);
    const posts = [];
    await page.route('**/api/v1/campaign/cycles/1/battles', route => route.fulfill({ json: { battles: [detail] } }));
    await page.route('**/api/v1/campaign/cycles/battles/1', route => route.fulfill({ json: detail }));
    await page.route('**/api/v1/campaign/cycles/battles/1/ownership', route => {
      if (route.request().method() === 'GET') return route.fulfill({ json: {
        battle_id: 1, territory_id: 2, current_cycle_id: 1, current_owner_clan_id: 2,
        current_owner_name: 'Second clan', preview_token: token,
        choices: [{ clan_id: null, clan_name: null }, { clan_id: 1, clan_name: 'First clan' },
          { clan_id: 2, clan_name: 'Second clan' }],
      } });
      const payload = route.request().postDataJSON();
      posts.push(payload);
      if (posts.length === 1) {
        token = 'b'.repeat(64);
        return route.fulfill({ status: 409, json: { detail: 'Ownership preview changed; refresh before confirming' } });
      }
      detail = { ...detail, current_owner_clan_id: 1, current_owner_name: 'First clan',
        ownership_corrections: [{ id: 1, previous_owner_clan_id: 2, new_owner_clan_id: 1,
          reason: payload.reason, applied_at: '2026-10-17T01:05:00Z' }] };
      return route.fulfill({ json: detail });
    });
    await page.goto('/campaign/cycles/1?territory=2');
    await page.getByRole('tab', { name: /Управление/ }).click();
    const open = page.getByRole('button', { name: 'Изменить владельца территории', exact: true });
    await expect(open).toBeVisible();
    expect(posts).toHaveLength(0);
    await open.click();
    const form = page.getByRole('form', { name: 'Исправление владения' });
    await expect(form).toContainText('Текущий владелец: Second clan');
    await form.getByLabel('Новый владелец', { exact: true }).selectOption('1');
    await form.getByLabel('Причина', { exact: true }).fill('Проверено администратором');
    const submit = form.getByRole('button', { name: 'Подтвердить передачу', exact: true });
    await expect(submit).toBeDisabled();
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    await page.screenshot({ path: `test-results/cycle-ownership-preview-${width}.png`, fullPage: true });
    await form.getByRole('checkbox').check();
    await submit.click();
    await expect(form.getByRole('alert')).toBeVisible();
    await form.getByRole('button', { name: 'Обновить данные владельца' }).click();
    await expect(form.getByRole('checkbox')).not.toBeChecked();
    await form.getByLabel('Новый владелец', { exact: true }).selectOption('1');
    await form.getByRole('checkbox').check();
    await submit.click();
    await expect(page.locator('.cycle-ownership-current')).toContainText('First clan');
    await page.getByRole('tab', { name: /История/ }).click();
    await expect(page.locator('.cycle-ownership-history')).toContainText('Проверено администратором');
    expect(posts).toHaveLength(2);
    expect(posts[0].preview_token).toBe('a'.repeat(64));
    expect(posts[1].preview_token).toBe('b'.repeat(64));
    expect(posts[1].command_id).not.toBe(posts[0].command_id);
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    await page.screenshot({ path: `test-results/cycle-ownership-${width}.png`, fullPage: true });
  });
}
