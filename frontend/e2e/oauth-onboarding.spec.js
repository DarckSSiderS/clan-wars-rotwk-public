import { expect, test } from '@playwright/test';

const guestSession = {
  id: 17,
  username: 'ArenaKnight',
  display_name: 'Arena Knight',
  email: null,
  is_active: true,
  is_claimed: true,
  balance: 730,
  level: 4,
  experience: 1250,
  avatar_url: '/images/users/arena-knight.png',
  language: 'ru',
  allow_clan_invites: false,
  telegram_url: 'https://t.me/arena_knight',
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

const onboardingSession = {
  ...guestSession,
  onboarding_completed_at: null,
  history_mode: null,
  statistics_started_at: null,
  onboarding_required: true,
};

const homeSummary = {
  clan_players: 12,
  total_clans: 4,
  territories: { total: 76, occupied: 9, contested: 1, free: 67 },
  active_wars: [],
  recent_territory_changes: [],
  top_clans: [],
};

const json = (route, payload, status = 200, headers = {}) => route.fulfill({
  status,
  headers,
  contentType: 'application/json',
  body: JSON.stringify(payload),
});

const installApi = async (page, options = {}) => {
  let session = options.session ?? null;
  const requests = [];

  await page.addInitScript(({ seedLegacyStorage }) => {
    window.localStorage.clear();
    window.sessionStorage.clear();
    window.localStorage.setItem('language', 'ru');
    if (seedLegacyStorage) {
      for (const key of ['token', 'user', 'admin_token', 'original_admin']) {
        window.localStorage.setItem(key, `local-${key}`);
        window.sessionStorage.setItem(key, `session-${key}`);
      }
    }
  }, { seedLegacyStorage: options.seedLegacyStorage === true });

  await page.route('**/api/v1/**', async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    requests.push({
      method: request.method(),
      pathname: url.pathname,
      search: url.search,
      authorization: request.headers().authorization,
      body: request.postDataJSON?.(),
    });

    if (url.pathname === '/api/v1/statistics/home') return json(route, homeSummary);
    if (url.pathname === '/api/v1/auth/session') {
      return session
        ? json(route, session)
        : json(route, { detail: { code: 'invalid_session' } }, 401);
    }
    if (url.pathname === '/api/v1/auth/password-login') {
      if (options.passwordFailure) {
        return json(route, { detail: { code: 'invalid_credentials' } }, 401);
      }
      session = options.passwordSession || guestSession;
      return json(route, session, 200, { 'set-cookie': 'cw_session=test; Path=/; HttpOnly' });
    }
    if (url.pathname === '/api/v1/auth/onboarding') {
      session = guestSession;
      return json(route, session, 200, { 'set-cookie': 'cw_session=rotated; Path=/; HttpOnly' });
    }
    if (url.pathname === '/api/v1/auth/logout') {
      session = null;
      return route.fulfill({ status: 204 });
    }
    if (url.pathname === '/api/v1/clans/') {
      return options.expireGameplay
        ? json(route, { detail: { code: 'invalid_session' } }, 401)
        : json(route, []);
    }
    if (url.pathname === '/api/v1/clans/my') return json(route, { detail: 'No clan' }, 404);
    if (url.pathname === '/api/v1/users/me') return json(route, guestSession);

    return json(route, {});
  });

  return requests;
};

test('public home stays available when the cookie session is absent', async ({ page }) => {
  const requests = await installApi(page);

  await page.goto('/');

  await expect(page.locator('h1', { hasText: 'Война за Средиземье' })).toBeVisible();
  expect(requests.some(({ pathname }) => pathname === '/api/v1/auth/session')).toBe(true);
});

test('guest sees the existing login dialog on a protected route', async ({ page }) => {
  await installApi(page);

  await page.goto('/clans');

  const dialog = page.getByRole('dialog', { name: 'Войдите, чтобы продолжить' });
  await expect(dialog).toBeVisible();
  await expect(dialog.getByRole('button', { name: 'Войти через BFME Arena' })).toBeVisible();
  await expect(page.locator('h1', { hasText: 'Война за Средиземье' })).toBeVisible();
});

test('Arena login navigates to the backend with an internal return path', async ({ page }) => {
  await installApi(page);
  await page.goto('/login', { waitUntil: 'networkidle' });

  const arenaRequest = page.waitForRequest((request) => (
    request.url().includes('/api/v1/auth/arena/start?')
  ));
  await page.getByRole('button', { name: 'Войти через BFME Arena' }).click();

  const request = await arenaRequest;
  expect(new URL(request.url()).searchParams.get('return_to')).toBe('/');
});

test('password fallback sends nickname credentials and shows a safe error', async ({ page }) => {
  const requests = await installApi(page, { passwordFailure: true });
  await page.goto('/login');

  const fallback = page.getByRole('button', { name: 'Войти по паролю' });
  await expect(fallback).toHaveAttribute('aria-expanded', 'false');
  await fallback.click();
  await expect(fallback).toHaveAttribute('aria-expanded', 'true');

  await page.getByRole('textbox', { name: 'Ник BFME Arena' }).fill('ArenaKnight');
  await page.getByLabel('Пароль').fill('wrong-password');
  await page.getByRole('button', { name: 'Войти', exact: true }).click();

  await expect(page.getByRole('alert')).toHaveText('Неверный ник Arena или пароль.');
  const login = requests.find(({ pathname }) => pathname === '/api/v1/auth/password-login');
  expect(login.body).toEqual({ nickname: 'ArenaKnight', password: 'wrong-password' });
});

test('OAuth callback errors are localized without reflecting external details', async ({ page }) => {
  await installApi(page);

  await page.goto('/login?oauth_error=access_denied&error_description=TOP_SECRET');

  await expect(page.getByRole('alert')).toHaveText('Вход через Arena отменён. Разрешение не было предоставлено.');
  await expect(page.getByText('TOP_SECRET')).toHaveCount(0);
});

test('onboarding requires history, language, rules and matching optional password', async ({ page }) => {
  const requests = await installApi(page, { session: onboardingSession });
  await page.goto('/wars');

  await expect(page).toHaveURL(/\/onboarding$/);
  await expect(page.getByRole('heading', { level: 1, name: 'Настройка профиля' })).toBeVisible();
  await expect(
    page.getByRole('paragraph')
      .filter({ hasText: 'BFME Arena подтвердила профиль:' })
      .getByText('Arena Knight', { exact: true }),
  ).toBeVisible();

  await page.getByRole('radio', { name: /Полная история Arena/ }).check();
  await page.getByRole('combobox', { name: 'Язык интерфейса' }).selectOption('de');
  const submit = page.getByRole('button', { name: 'Завершить настройку' });
  await expect(submit).toBeDisabled();
  await expect(page.getByText('Чтобы продолжить, примите правила проекта и обработки данных.')).toBeVisible();

  await page.getByRole('checkbox', { name: /Я принимаю правила/ }).check();
  await page.getByLabel('Локальный пароль', { exact: true }).fill('long-password-one');
  await page.getByLabel('Подтвердите локальный пароль').fill('long-password-two');
  await submit.click();
  await expect(page.getByRole('alert')).toHaveText('Пароли не совпадают.');

  await page.getByLabel('Подтвердите локальный пароль').fill('long-password-one');
  await submit.click();

  await expect(page).toHaveURL(/\/profile$/);
  const onboarding = requests.find(({ pathname }) => pathname === '/api/v1/auth/onboarding');
  expect(onboarding.body).toEqual({
    history_mode: 'full',
    language: 'de',
    accepted_rules: true,
    password: 'long-password-one',
  });
});

test('completed users cannot remain on onboarding', async ({ page }) => {
  await installApi(page, { session: guestSession });

  await page.goto('/onboarding');

  await expect(page).toHaveURL(/\/profile$/);
});

test('registration stays available without restoring browser token auth', async ({ page }) => {
  const requests = await installApi(page);
  await page.goto('/register');

  await expect(page).toHaveURL('/register');
  await expect(page.getByRole('tab', { name: 'Регистрация' })).toHaveAttribute('aria-selected', 'true');

  await page.goto('/login');
  await page.getByRole('button', { name: 'Войти по паролю' }).click();
  await page.getByRole('textbox', { name: 'Ник BFME Arena' }).fill('ArenaKnight');
  await page.getByLabel('Пароль').fill('valid-password');
  await page.getByRole('button', { name: 'Войти', exact: true }).click();

  const storage = await page.evaluate(() => ({
    localToken: localStorage.getItem('token'),
    localUser: localStorage.getItem('user'),
    sessionToken: sessionStorage.getItem('token'),
  }));
  expect(storage).toEqual({ localToken: null, localUser: null, sessionToken: null });
  expect(requests.every(({ authorization }) => !authorization)).toBe(true);
});

test('startup removes legacy auth values from both browser storages', async ({ page }) => {
  await installApi(page, { seedLegacyStorage: true });

  await page.goto('/');

  const storage = await page.evaluate(() => Object.fromEntries(
    ['token', 'user', 'admin_token', 'original_admin'].flatMap((key) => [
      [`local:${key}`, localStorage.getItem(key)],
      [`session:${key}`, sessionStorage.getItem(key)],
    ]),
  ));
  expect(storage).toEqual({
    'local:token': null,
    'session:token': null,
    'local:user': null,
    'session:user': null,
    'local:admin_token': null,
    'session:admin_token': null,
    'local:original_admin': null,
    'session:original_admin': null,
  });
  expect(await page.evaluate(() => localStorage.getItem('language'))).toBe('ru');
});

test('a post-bootstrap 401 expires the React session without a bootstrap loop', async ({ page }) => {
  const requests = await installApi(page, {
    session: guestSession,
    expireGameplay: true,
  });

  await page.goto('/clans');

  await expect(page.getByRole('dialog', { name: 'Войдите, чтобы продолжить' })).toBeVisible();
  expect(requests.filter(({ pathname }) => pathname === '/api/v1/auth/session')).toHaveLength(1);
});
