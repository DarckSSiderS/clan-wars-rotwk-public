import { test, expect } from '@playwright/test';

const user = { id: 1, username: 'Head', language: 'ru', is_verified: true, is_claimed: true,
  role: { name: 'admin' }, onboarding_completed: true };
const clan = { id: 11, name: 'Our clan', leader_id: 1, created_at: '2026-01-01T00:00:00Z', member_count: 1 };
const battle = { id: 31, season_id: 2, cycle_id: 7, territory_id: 10, territory_name: 'Home',
  completed_at: null, winner_clan_id: null, adjustments: [],
  sides: [{ clan_id: 11, clan_name: 'Our clan', role: 'defense', score: '12.5', members: [{ user_id: 1, username: 'Head' }] },
    { clan_id: 22, clan_name: 'Their clan', role: 'attack', score: '-3.25', members: [] }],
  contributions: [{ replay_id: 'replay-1', user_id: 1, clan_id: 11, points: '12.5', counted: true, reason: 'counted' }] };

async function mock(page, { mode = 'cycle_v1' } = {}) {
  const requests = [], posts = [];
  const detail = structuredClone(battle);
  let fail = false;
  await page.addInitScript(() => localStorage.setItem('language', 'ru'));
  await page.route('**/api/v1/**', route => {
    const request = route.request(), path = new URL(request.url()).pathname;
    requests.push(path);
    let json = [];
    if (path.endsWith('/auth/session') || path.endsWith('/users/me')) json = user;
    else if (path === '/api/v1/campaign/cycles/current') json = { mechanics_version: mode, cycle: { id: 7 }, territory_battles: [{ battle_id: 31, territory_id: 10 }] };
    else if (/\/campaign\/cycles\/[78]$/.test(path)) json = { id: Number(path.split('/').at(-1)), number: 2, season_id: 2, phase: 'battle' };
    else if (path === '/api/v1/campaign/cycles/7/battles') json = { battles: [detail] };
    else if (path === '/api/v1/campaign/cycles/8/battles') json = { battles: [] };
    else if (path === '/api/v1/campaign/cycles/battles/31') {
      if (fail) return route.fulfill({ status: 503, json: { detail: 'Refresh offline' } });
      json = detail;
    } else if (path.endsWith('/battles/31/adjustments')) {
      posts.push(request.postDataJSON());
      return posts.length === 1 ? route.abort('failed') : route.fulfill({ json: detail });
    } else if (path === '/api/v1/campaign/cycles/clans/11/history') json = { season_id: 2, battles: [detail] };
    else if (path === '/api/v1/campaign/cycles/7/clans/11/planning') json = { snapshot_ready: true, clan_id: 11,
      members: [{ user_id: 1, eligible: true }, { user_id: 2, eligible: true }, { user_id: 3, eligible: false, scouting: true }],
      plan: { orders: [{ user_id: 1, kind: 'reserve' }] }, defence_targets: [10] };
    else if (path === '/api/v1/campaign/cycles/7/clans/11/preparation') json = { scout: { request: { scout_user_id: 3 } } };
    else if (path === '/api/v1/campaign/cycles/economy/seasons/2/clans/11/context') json = { state: { active_relics: ['tree'], relics: { tree: 1 } } };
    else if (path === '/api/v1/clans/my' || path === '/api/v1/clans/11') json = clan;
    else if (path === '/api/v1/clans/11/members') json = [{ id: 1, user_id: 1, username: 'Head', rank: 'Глава клана' }];
    else if (path === '/api/v1/clans/market/offers') json = { offers: [], clan_activity: [], caravans: [] };
    else if (path.includes('/wars/clan/')) json = [{ id: 99, status: 'completed', territory_name: 'Legacy land', attacking_clan_id: 11,
      defending_clan_id: 22, defending_clan_name: 'Old opponent', winner_clan_id: 11, started_at: '2025-01-01T00:00:00Z' }];
    else if (path.includes('/stats')) json = { total_matches: 0, wins: 0, losses: 0, win_rate: 0, elo_ratings: {} };
    else if (path.includes('notifications')) json = { items: [], unread_count: 0, total: 0 };
    else if (path.includes('presence')) json = { items: [] };
    return route.fulfill({ json });
  });
  return { detail, requests, posts, failRefresh: value => { fail = value; } };
}

test('cycle overview links real battles and Show all opens history with a separate legacy archive', async ({ page }) => {
  const s = await mock(page);
  await page.goto('/clans/11');
  const recent = page.locator('.clan-overview-battles');
  await expect(recent.getByRole('link', { name: 'Home', exact: true })).toHaveAttribute('href', '/campaign/cycles/7?territory=10');
  await expect(recent).toContainText('12.5');
  await expect(recent).not.toContainText('Old opponent');
  expect(s.requests.some(path => path.includes('/wars/clan/'))).toBe(false);
  await page.locator('.clan-prototype-overview .section-head .text-btn').click();
  await expect(page).toHaveURL(/tab=history$/);
  await expect(page.locator('.clan-history-panel').getByRole('link', { name: 'Home', exact: true })).toBeVisible();
  await page.locator('.clan-legacy-archive > summary').click();
  await expect(page.locator('.clan-legacy-archive').getByRole('link')).toHaveAttribute('href', '/battles/99');
  await page.locator('.clan-history-panel').getByRole('link', { name: 'Home', exact: true }).click();
  await expect(page.locator('.cycle-detail')).toBeVisible();
});

test('legacy overview still uses wars and Show all opens the retained history', async ({ page }) => {
  const s = await mock(page, { mode: 'legacy' });
  await page.goto('/clans/11');
  await expect(page.locator('.clan-overview-battles')).toContainText('Old opponent');
  await page.locator('.clan-prototype-overview .section-head .text-btn').click();
  await expect(page).toHaveURL(/tab=history$/);
  expect(s.requests.some(path => path.endsWith('/clans/11/history'))).toBe(false);
});

test('poll and refresh preserve open match, drafts and uncertain command ID even after refresh error', async ({ page }) => {
  const s = await mock(page);
  await page.clock.install();
  await page.goto('/campaign/cycles/7?territory=10');
  const match = page.locator('.cycle-match').first();
  await match.locator(':scope > summary').click();
  await page.getByRole('tab', { name: /Управление/ }).click();
  const form = page.locator('.cycle-admin-tools form.cycle-admin');
  await form.evaluate(element => { element.dataset.pollIdentity = 'original'; });
  await form.getByLabel('Изменение очков', { exact: true }).fill('25');
  await form.getByRole('textbox', { name: 'Причина', exact: true }).fill('Неопределённый ответ');
  await form.getByRole('button', { name: 'Сохранить', exact: true }).click();
  await expect(form.getByRole('alert')).toBeVisible();
  s.detail.contributions.push({ replay_id: 'new-match', user_id: 1, clan_id: 11, points: '1', counted: true, reason: 'counted' });
  await page.clock.fastForward(30_100);
  await expect(page.locator('.cycle-match')).toHaveCount(2);
  s.failRefresh(true);
  await page.getByRole('button', { name: 'Обновить', exact: true }).click();
  await expect(page.locator('.cycle-detail > [role="alert"]')).toBeVisible();
  await expect(form).toHaveAttribute('data-poll-identity', 'original');
  await expect(form.getByRole('textbox', { name: 'Причина', exact: true })).toHaveValue('Неопределённый ответ');
  s.failRefresh(false);
  await form.getByRole('button', { name: 'Сохранить', exact: true }).click();
  await expect(form.getByRole('status')).toBeVisible();
  expect(s.posts).toHaveLength(2);
  expect(s.posts[1]).toEqual(s.posts[0]);
  await page.getByRole('tab', { name: /Матчи/ }).click();
  await expect(match).toHaveAttribute('open', '');
});

test('hidden tab pauses polling, visibility resumes, and a slow GET never overlaps another GET', async ({ page }) => {
  const s = await mock(page);
  await page.clock.install();
  await page.goto('/campaign/cycles/7?territory=10');
  await expect(page.locator('.cycle-detail')).toBeVisible();
  const reads = () => s.requests.filter(path => path === '/api/v1/campaign/cycles/battles/31').length;
  const before = reads();
  await page.evaluate(() => { Object.defineProperty(document, 'hidden', { configurable: true, value: true }); document.dispatchEvent(new Event('visibilitychange')); });
  await page.clock.fastForward(120_000);
  expect(reads()).toBe(before);
  let release;
  const gate = new Promise(resolve => { release = resolve; });
  let slowReads = 0;
  await page.route('**/api/v1/campaign/cycles/battles/31', async route => {
    slowReads++;
    await gate;
    await route.fulfill({ json: battle }).catch(() => {});
  });
  await page.evaluate(() => { Object.defineProperty(document, 'hidden', { configurable: true, value: false }); document.dispatchEvent(new Event('visibilitychange')); });
  await expect.poll(() => slowReads).toBe(1);
  await page.clock.fastForward(120_000);
  expect(slowReads).toBe(1);
  await page.getByRole('link', { name: 'Кланы', exact: true }).click();
  release();
  await expect(page.locator('.cycle-detail')).toHaveCount(0);
  await page.clock.fastForward(120_000);
  expect(slowReads).toBe(1);
});

test('changing the cycle URL cannot show the preceding battle while a new GET waits', async ({ page }) => {
  await mock(page);
  await page.goto('/campaign/cycles/7?territory=10');
  await expect(page.locator('.cycle-detail')).toBeVisible();
  let release;
  const gate = new Promise(resolve => { release = resolve; });
  await page.route('**/api/v1/campaign/cycles/8/battles', async route => { await gate; await route.fulfill({ json: { battles: [] } }); });
  await page.evaluate(() => { history.pushState({}, '', '/campaign/cycles/8?territory=10'); dispatchEvent(new PopStateEvent('popstate')); });
  await expect(page.locator('.cycle-detail')).toHaveCount(0);
  await expect(page.locator('.cycle-loading')).toBeVisible();
  release();
  await expect(page.locator('.cycle-empty')).toBeVisible();
});

for (const width of [390, 1440]) {
  test(`own readiness stays compact and does not request foreign context at ${width}px`, async ({ page }) => {
    await page.setViewportSize({ width, height: 1000 });
    const s = await mock(page);
    await page.goto('/campaign/cycles/7?clan=22');
    const summary = page.locator('.cycle-readiness');
    await expect(summary).toContainText('Свободные игроки');
    await expect(summary).toContainText('Неприкрытые земли');
    await expect(summary).toContainText('Назначен');
    expect(s.requests.some(path => /clans\/22\/(preparation|planning|context)/.test(path))).toBe(false);
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    await page.screenshot({ path: `test-results/clan-history-readiness-${width}.png`, fullPage: true });
  });
}
