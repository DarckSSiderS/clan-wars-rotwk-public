import { expect, test } from '@playwright/test';

const user = {
  id: 17,
  username: 'guest-login-test',
  display_name: 'Guest Login Test',
  email: null,
  is_active: true,
  is_claimed: true,
  balance: 730,
  level: 4,
  experience: 1250,
  language: 'ru',
  avatar_url: null,
  allow_clan_invites: true,
  telegram_url: null,
  twitch_url: null,
  youtube_url: null,
  role: { id: 2, name: 'user', description: 'Player' },
  created_at: '2026-08-20T09:30:00Z',
  onboarding_completed_at: '2026-08-22T12:00:00Z',
  history_mode: 'new',
  statistics_started_at: '2026-08-22T12:00:00Z',
  external_identity_status: 'verified',
  onboarding_required: false,
};

const homeSummary = {
  clan_players: 12,
  total_clans: 4,
  territories: { total: 76, occupied: 9, contested: 1, free: 67 },
  active_wars: [],
  recent_territory_changes: [],
  top_clans: [],
};

const json = (route, payload, status = 200) => route.fulfill({
  status,
  contentType: 'application/json',
  body: JSON.stringify(payload),
});

test.beforeEach(async ({ page }) => {
  let session = null;
  await page.addInitScript(() => {
    window.localStorage.clear();
    window.sessionStorage.clear();
    window.localStorage.setItem('language', 'ru');
  });

  await page.route('**/api/v1/**', async (route) => {
    const request = route.request();
    const { pathname } = new URL(request.url());

    if (pathname === '/api/v1/statistics/home') return json(route, homeSummary);
    if (pathname === '/api/v1/auth/session') {
      return session
        ? json(route, session)
        : json(route, { detail: { code: 'invalid_session' } }, 401);
    }
    if (pathname === '/api/v1/auth/password-login') {
      session = user;
      return json(route, user);
    }
    if (pathname === '/api/v1/users/me') return json(route, user);
    if (pathname === '/api/v1/clans/') return json(route, []);
    if (pathname === '/api/v1/clans/my') return json(route, { detail: 'No clan' }, 404);
    if (pathname === '/api/v1/clans/diplomacy') return json(route, []);
    if (pathname === '/api/v1/wars/') return json(route, []);

    return json(route, {});
  });
});

test('guest sees public home and all primary destinations in navigation', async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto('/');

  await expect(page.getByRole('heading', { level: 1, name: 'Война за Средиземье' })).toBeVisible();
  await expect(page.getByRole('link', { name: 'Кланы', exact: true })).toBeVisible();
  await expect(page.getByRole('link', { name: 'Статистика', exact: true })).toBeVisible();
  await expect(page.getByRole('link', { name: 'Битвы', exact: true })).toBeVisible();
  await expect(page.getByRole('link', { name: 'Карта', exact: true })).toBeVisible();
});

test('guest opens a protected destination in a login dialog over the home page', async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto('/clans');

  await expect(page).toHaveURL(/\/clans$/);
  await expect(page.locator('h1', { hasText: 'Война за Средиземье' })).toBeVisible();
  const dialog = page.getByRole('dialog', { name: 'Войдите, чтобы продолжить' });
  await expect(dialog).toBeVisible();
  expect(await dialog.evaluate((element) => element.contains(document.activeElement))).toBe(true);

  await dialog.getByRole('button', { name: 'Закрыть' }).click();
  await expect(page).toHaveURL('/');
});

test('successful dialog login opens the originally requested destination', async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto('/clans');

  const dialog = page.getByRole('dialog', { name: 'Войдите, чтобы продолжить' });
  await dialog.getByRole('button', { name: 'Войти по паролю' }).click();
  await dialog.getByRole('textbox', { name: 'Ник BFME Arena' }).fill('guest-login-test');
  await dialog.getByLabel('Пароль').fill('admin');
  await dialog.getByRole('button', { name: 'Войти', exact: true }).click();

  await expect(page).toHaveURL(/\/clans$/);
  await expect(page.getByRole('heading', { level: 1, name: 'Кланы' })).toBeVisible();
  await expect(dialog).toBeHidden();
});
