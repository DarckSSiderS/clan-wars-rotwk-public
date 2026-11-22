import { expect, test } from '@playwright/test';

const target = {
  id: 22,
  username: 'target-player',
  display_name: 'Target Player',
  email: null,
  is_active: false,
  is_claimed: false,
  balance: 100,
  level: 2,
  experience: 40,
  avatar_url: null,
  language: 'ru',
  allow_clan_invites: true,
  telegram_url: null,
  twitch_url: null,
  youtube_url: null,
  role: { id: 2, name: 'user', description: 'Player' },
  created_at: '2026-08-20T09:30:00Z',
  onboarding_completed_at: '2026-08-22T12:00:00Z',
  history_mode: 'new',
  statistics_started_at: '2026-08-22T12:00:00Z',
  external_identity_status: null,
  onboarding_required: false,
  is_admin_impersonation: true,
  impersonated_by_username: 'ActualOperator',
};

const admin = {
  ...target,
  id: 1,
  username: 'ActualOperator',
  display_name: 'Real Admin',
  is_active: true,
  is_claimed: true,
  role: { id: 1, name: 'admin', description: 'Administrator' },
  is_admin_impersonation: false,
  impersonated_by_username: null,
};

const homeSummary = {
  clan_players: 0,
  total_clans: 0,
  territories: { total: 76, occupied: 0, contested: 0, free: 76 },
  active_wars: [],
  recent_territory_changes: [],
  top_clans: [],
};

const json = (route, payload, status = 200) => route.fulfill({
  status,
  contentType: 'application/json',
  body: JSON.stringify(payload),
});

const openImpersonatedHome = async (page, returnStatus = 200) => {
  let session = target;
  await page.addInitScript(() => {
    window.localStorage.setItem('language', 'ru');
  });
  await page.route('**/api/v1/**', async (route) => {
    const { pathname } = new URL(route.request().url());
    if (pathname === '/api/v1/auth/session') return json(route, session);
    if (pathname === '/api/v1/statistics/home') return json(route, homeSummary);
    if (pathname === '/api/v1/auth/impersonation/return') {
      await new Promise((resolve) => setTimeout(resolve, 700));
      if (returnStatus !== 200) {
        return json(route, { detail: { code: 'session_transition_failed' } }, returnStatus);
      }
      session = admin;
      return json(route, admin);
    }
    return json(route, {});
  });
  await page.goto('/');
};

test('server actor name is visible and return replaces the effective session', async ({ page }) => {
  await openImpersonatedHome(page);

  const banner = page.getByRole('region', { name: 'Режим просмотра пользователя' });
  await expect(banner).toBeVisible();
  await expect(banner).toContainText('Target Player');
  await expect(banner).toContainText('ActualOperator');
  const button = banner.getByRole('button', { name: 'Вернуться к администратору' });
  await button.click();
  await expect(banner.getByRole('button')).toBeDisabled();
  await expect(banner).toHaveAttribute('aria-busy', 'true');
  await expect(banner).toBeHidden();
  await expect(page.getByRole('button', { name: 'Профиль' })).toBeVisible();
});

test('failed return keeps the banner and exposes an accessible error', async ({ page }) => {
  await openImpersonatedHome(page, 503);

  const banner = page.getByRole('region', { name: 'Режим просмотра пользователя' });
  await banner.getByRole('button', { name: 'Вернуться к администратору' }).click();

  await expect(banner).toBeVisible();
  await expect(banner.getByRole('alert')).toHaveText(
    'Не удалось вернуться в административную сессию. Повторите попытку.',
  );
  await expect(
    banner.getByRole('button', { name: 'Вернуться к администратору' }),
  ).toBeEnabled();
});
