import { test, expect } from '@playwright/test';

const user = { id: 1, username: 'Head', language: 'ru', is_verified: true, is_claimed: true,
  role: { name: 'user' }, onboarding_completed: true };
const battle = {
  cycle_id: 1, dispatch_id: 'dispatch / 1', territory_id: 10, territory_name: 'Арнор',
  phase: 'completed', outcome: 'exhausted', server_time: '2026-10-17T14:05:00Z',
  starts_at: '2026-10-17T02:00:00Z', ends_at: '2026-10-17T14:00:00Z',
  replay_deadline: '2026-10-17T14:05:00Z', arrives_at: '2026-10-18T00:00:00Z',
  sides: [
    { clan_id: 7, clan_name: 'Akatsuki', role: 'help', score: '100', members: [{ user_id: 2, username: 'Renamed helper', positive_points: '200', negative_points: '-100', total_points: '100' }] },
    { clan_id: 8, clan_name: 'First ambush', role: 'ambush', score: '60', members: [{ user_id: 3, username: 'Ambush One' }] },
    { clan_id: 9, clan_name: 'Second ambush', role: 'ambush', score: '60', members: [{ user_id: 4, username: 'Ambush Two' }] },
  ],
  contributions: [
    { replay_id: 'bfmeladder:game-1', user_id: 2, clan_id: 7, points: '200', counted: true, reason: 'counted',
      calculation: { historical_elo: '1200', base_points: '100', victory_bonus_percent: '0', direct_multiplier: 2, exhaustion_multiplier: '1' } },
    { replay_id: 'bfmeladder:game-1', user_id: 3, clan_id: 8, points: '0', counted: false, reason: 'ambush_opponent', calculation: {} },
  ],
};

async function mock(page, response = battle) {
  await page.addInitScript(() => localStorage.setItem('language', 'ru'));
  await page.route('**/api/v1/**', route => {
    const url = new URL(route.request().url());
    const path = url.pathname;
    let payload = {};
    if (path.endsWith('/auth/session') || path.endsWith('/users/me')) payload = user;
    else if (path.endsWith('/interception')) {
      expect(url.searchParams.get('dispatch_id')).toBe('dispatch / 1');
      payload = response;
    } else if (path.includes('notifications')) payload = { items: [], total: 0, unread_count: 0 };
    else if (path.includes('presence')) payload = { items: [] };
    else if (path.includes('localization')) payload = [];
    return route.fulfill({ json: payload });
  });
}

for (const width of [390, 1440]) {
  test(`interception details retain independent sides and explain rejected games at ${width}px`, async ({ page }) => {
    await page.setViewportSize({ width, height: 1000 });
    await mock(page);
    const errors = []; page.on('pageerror', error => errors.push(error.message));
    await page.goto('/campaign/cycles/1/interception?dispatch=dispatch%20%2F%201');
    await expect(page.getByRole('heading', { name: 'Перехват подкрепления', exact: true })).toBeVisible();
    await expect(page.locator('.ci-result')).toContainText('Подкрепление продолжает путь с половиной вклада.');
    await expect(page.locator('.ci-sides > li')).toHaveCount(3);
    await page.locator('.cycle-match > summary').click();
    await expect(page.getByRole('heading', { name: 'Renamed helper', exact: true })).toBeVisible();
    await expect(page.getByText('Соперник участвует в другой засаде этого перехвата', { exact: false })).toBeVisible();
    await expect(page.getByText('Elo на момент матча', { exact: true }).first()).toBeVisible();
    await expect(page.getByRole('link', { name: 'Битва за территорию', exact: true })).toHaveAttribute('href', '/campaign/cycles/1?territory=10');
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    expect(errors).toEqual([]);
    await page.evaluate(() => window.scrollTo({ top: 0, behavior: 'instant' }));
    await page.screenshot({ path: `test-results/cycle-interception-${width}.png`, fullPage: true });
  });
}

test('interception failure offers retry without showing stale battle data', async ({ page }) => {
  await mock(page);
  let failed = true;
  await page.route('**/api/v1/campaign/cycles/1/interception?*', route => failed
    ? route.fulfill({ status: 503, json: { detail: 'Unavailable' } }) : route.fulfill({ json: battle }));
  await page.goto('/campaign/cycles/1/interception?dispatch=dispatch%20%2F%201');
  await expect(page.getByRole('alert')).toBeVisible();
  await expect(page.locator('.ci-sides')).toHaveCount(0);
  failed = false;
  await page.getByRole('button', { name: 'Обновить', exact: true }).click();
  await expect(page.locator('.ci-sides > li')).toHaveCount(3);
});
