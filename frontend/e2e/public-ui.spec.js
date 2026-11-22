import { expect, test } from '@playwright/test';

const testUser = {
  id: 7,
  username: 'layout-admin',
  nickname: 'Layout Administrator',
  language: 'ru',
  is_verified: true,
  avatar_url: null,
  balance: 1000,
  role: { name: 'admin' },
};

test('archive is a primary header destination and selects nested archive pages', async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto('/seasons/1');
  const link = page.locator('header').getByRole('link', { name: 'Архив сезонов', exact: true });
  await expect(link).toBeVisible();
  await expect(link).toHaveAttribute('aria-current', 'page');
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBe(1440);
});

test('manual season launch uses the new transactional endpoint and retries the same command', async ({ page }) => {
  const writes = [];
  await page.route('**/api/v1/campaign/seasons', route => json(route, { seasons: [{ id: 1, number: 1, name: 'Первый сезон', status: 'completed' }] }));
  await page.route('**/api/v1/campaign/seasons/start', route => {
    writes.push(route.request().postDataJSON());
    return writes.length === 1 ? route.abort('failed') : json(route, { season_id: 2 });
  });
  await page.goto('/admin');
  await page.getByRole('tab', { name: 'Сезоны', exact: true }).click();
  await page.getByRole('button', { name: 'Запустить новый сезон', exact: true }).click();
  let dialog = page.getByRole('dialog', { name: 'Запуск кампании' });
  await dialog.getByRole('textbox', { name: 'Название', exact: true }).fill('Второй сезон');
  await expect(dialog).toContainText('72 часа');
  await expect(dialog.getByRole('spinbutton')).toHaveCount(0);
  await dialog.getByRole('button', { name: 'Запустить', exact: true }).click();
  await expect.poll(() => writes.length).toBe(1);
  await expect(dialog.getByRole('textbox', { name: 'Название', exact: true })).toBeDisabled();
  await page.reload();
  await page.getByRole('tab', { name: 'Сезоны', exact: true }).click();
  await page.getByRole('button', { name: 'Запустить новый сезон', exact: true }).click();
  dialog = page.getByRole('dialog', { name: 'Запуск кампании' });
  await dialog.getByRole('button', { name: 'Запустить', exact: true }).click();
  await expect.poll(() => writes.length).toBe(2);
  expect(writes[1]).toEqual(writes[0]);
  expect(writes[0]).toMatchObject({ name: 'Второй сезон', previous_season_id: 1 });
  expect(writes[0].command_id).toBeTruthy();
});

test('clan opens before member statistics and orders the roster by responsibility', async ({ page }) => {
  let release;
  const statistics = new Promise(resolve => { release = resolve; });
  let pending = 0;
  await page.route('**/api/v1/clans/1', route => json(route, { id: 1, name: 'Проверка состава', leader_id: 10, created_at: '2026-01-01T00:00:00Z', level: 1 }));
  await page.route('**/api/v1/clans/1/members', route => json(route, [
    { id: 11, user_id: 11, username: 'Новичок', rank: 'Салага' },
    { id: 12, user_id: 12, username: 'Воин', rank: 'Воин' },
    { id: 13, user_id: 13, username: 'Торговец', is_trader: true },
    { id: 14, user_id: 14, username: 'Воевода', is_warlord: true },
    { id: 10, user_id: 10, username: 'Глава', rank: 'Салага' },
  ]));
  await page.route('**/api/v1/users/*/stats**', async route => { pending++; await statistics; await json(route, {}); });
  try {
    await page.goto('/clans/1?tab=members');
    await expect(page.getByRole('heading', { name: 'Проверка состава', exact: true })).toBeVisible();
    await expect.poll(() => pending).toBe(4);
    const rows = page.locator('.stats-table tbody tr');
    await expect(rows).toHaveCount(5);
    for (const [i, name] of ['Глава', 'Воевода', 'Торговец', 'Воин', 'Новичок'].entries()) await expect(rows.nth(i)).toContainText(name);
  } finally { release(); }
});

test('a visible later season clears an uncertain old launch instead of replaying it next season', async ({ page }) => {
  const key = 'cw:admin-cycle-command:season-start:7';
  await page.addInitScript(key => localStorage.setItem(key, JSON.stringify({ name: 'Уже запущенный', previous_season_id: 1, command_id: 'lost-response' })), key);
  await page.route('**/api/v1/campaign/seasons', route => json(route, { seasons: [{ id: 2, number: 2, name: 'Уже запущенный', status: 'active' }] }));
  await page.goto('/admin');
  await expect.poll(() => page.evaluate(key => localStorage.getItem(key), key)).toBe(null);
});

test('Palantir links and unlinks Discord through profile settings', async ({ page }) => {
  let discordId = null;
  await page.route('**/api/v1/discord/link', async (route) => {
    const method = route.request().method();
    if (method === 'POST') {
      const payload = route.request().postDataJSON();
      if (payload.code !== 'valid-discord-code-for-browser-test') {
        return route.fulfill({ status: 400, contentType: 'application/json', body: JSON.stringify({ detail: 'Код истёк. Получите новый через /link.' }) });
      }
      discordId = '1551937393144238201';
    }
    if (method === 'DELETE') {
      discordId = null;
      return route.fulfill({ status: 204 });
    }
    return route.fulfill({ contentType: 'application/json', body: JSON.stringify({ enabled: true, discord_user_id: discordId }) });
  });
  await page.goto('/profile?tab=settings');
  const dialog = page.getByRole('dialog', { name: 'Настройки профиля' });
  await expect(dialog).toBeVisible();
  await dialog.getByLabel('Код от Палантира').fill('expired-discord-code-for-browser-test');
  await dialog.getByRole('button', { name: 'Привязать Discord', exact: true }).click();
  await expect(dialog.getByRole('alert')).toContainText('Код истёк');
  await dialog.getByLabel('Код от Палантира').fill('valid-discord-code-for-browser-test');
  await dialog.getByRole('button', { name: 'Привязать Discord', exact: true }).click();
  await expect(dialog.getByRole('status')).toContainText('Discord привязан');
  await expect(dialog).toContainText('1551937393144238201');
  await dialog.getByRole('button', { name: 'Отключить Discord', exact: true }).click();
  await expect(dialog.getByRole('status')).toContainText('Привязка отключена');
  await expect(dialog.getByLabel('Код от Палантира')).toBeVisible();
});

const homeSummary = {
  season: {
    id: 3,
    number: 3,
    name: 'Война за Север',
    status: 'active',
    starts_at: '2026-08-07T12:00:00Z',
    ends_at: '2026-09-18T12:00:00Z',
    progress_percent: 43,
    goals: [],
  },
  clan_players: 42,
  total_clans: 5,
  territories: { total: 76, occupied: 12, contested: 1, free: 64 },
  active_wars: [
    {
      id: 9,
      territory_id: 15,
      territory_name: 'Тестовая территория',
      territory_svg_path_data: 'M807.5,262.6c0,0,23,25,15,48s-7,26-23,48s-3,45,12,69s33,50,30,76c-3,26-5,46-18,56s-16,20-28,23 s-26,14-26,14s-69-27-79-34s-23-24-48-21s-51,8-59-14s-23-47-23-59s-30-60-30-60s42,20,76,1s81-51,101-52s6-24,34-47 S807.5,262.6,807.5,262.6z',
      ends_at: '2026-08-14T12:00:00Z',
      attacking_clan: { id: 1, name: 'Хранители', map_color: '#b83b3b' },
      defending_clan: null,
    },
  ],
  recent_territory_changes: [
    {
      territory_id: 14,
      territory_name: 'Северная земля',
      territory_svg_path_data: 'M807.5,262.6c0,0,23,25,15,48s-7,26-23,48s-3,45,12,69s33,50,30,76c-3,26-5,46-18,56s-16,20-28,23 s-26,14-26,14s-69-27-79-34s-23-24-48-21s-51,8-59-14s-23-47-23-59s-30-60-30-60s42,20,76,1s81-51,101-52s6-24,34-47 S807.5,262.6,807.5,262.6z',
      clan_id: 1,
      clan_name: 'Хранители очень длинного названия клана',
      clan_avatar_url: null,
      clan_map_color: '#b83b3b',
      captured_at: '2026-08-10T12:00:00Z',
      war_id: 8,
    },
  ],
  top_clans: [
    {
      id: 1,
      name: 'Хранители очень длинного названия клана',
      member_count: 12,
      territory_points: 340,
      avatar_url: null,
    },
  ],
};

const currentCampaignRules = {
  rule_set: {
    id: 4,
    version: 4,
    values: {
      CAMPAIGN_STARTING_INFLUENCE: 100,
      CAMPAIGN_STARTING_GOLD: 100,
      CAMPAIGN_STARTING_IRON: 6,
      CAMPAIGN_STARTING_WOOD: 6,
      CAMPAIGN_STARTING_FOOD: 3,
      CAMPAIGN_STARTING_MITHRIL: 0,
      WAR_DURATION_HOURS: 60,
      CLAN_ATTACK_COOLDOWN_HOURS: 60,
      WAR_MIN_MATCH_DURATION_SECONDS: 120,
      TERRITORY_RESOURCE_READY_HOURS: 48,
      TERRITORY_RESOURCE_PAYOUT_HOURS: 24,
      POPULATION_DEVELOPMENT_BONUS_FIRST_LEVELS_PERCENT: 8,
      POPULATION_DEVELOPMENT_BONUS_LATER_LEVELS_PERCENT: 4,
      POPULATION_DEVELOPMENT_BONUS_BREAK_LEVEL: 5,
      POPULATION_INCOME_BONUS_CAP_PERCENT: 20,
      CARAVAN_HOURS_PER_STEP: 6,
      CARAVAN_SEA_HOURS_PER_STEP: 8,
      CARAVAN_MIN_GOLD_FEE: 10,
      CARAVAN_BASE_GOLD_FEE: 7,
      CARAVAN_DISTANCE_GOLD_FEE: 4,
      CARAVAN_VOLUME_STEP: 7,
      CARAVAN_VOLUME_GOLD_FEE: 1,
      ELO_START_RATING: 1000,
      ELO_PROVISIONAL_MATCHES: 30,
      ELO_PROVISIONAL_K: 40,
      ELO_REGULAR_K: 24,
      ELO_EXPECTED_SCORE_DIVISOR: 400,
    },
    complete: true,
  },
  season: homeSummary.season,
};

const matchPreview = 'data:image/svg+xml,%3Csvg xmlns="http://www.w3.org/2000/svg" width="640" height="360"%3E%3Crect width="640" height="360" fill="%23232922"/%3E%3Ctext x="320" y="190" text-anchor="middle" fill="%23d2be8c" font-size="42"%3EForност%3C/text%3E%3C/svg%3E';

const matchDetailFixture = {
  id: 72,
  match_id: 'arena-72',
  winner_player: 'GondorHero',
  winner_faction: 'Гондор',
  loser_player: 'MordorLord',
  loser_faction: 'Мордор',
  match_date: '2026-08-31T18:42:00Z',
  duration: 754,
  map_name: 'Форност',
  map_id: 301,
  map_preview_url: matchPreview,
  game_mode: '1v1',
  game_name: 'The Rise of the Witch-king',
  arena_id: 9137,
  patch_id: 12,
  patch_name: 'Ennorath 1.7',
  patch_version: '1.7',
  rating_patch_family: 'ennorath',
  elo_delta: 18,
  downloads: 14,
  likes: [{ id: 1 }],
  comments: [{ id: 2 }, { id: 3 }],
  is_valid: true,
  is_qualification_round: false,
  replay_supported: true,
  replay_archived: true,
  replay_file_size: 153600,
  replay_download_url: '/api/v1/statistics/matches/arena-72/replay',
  participants: [
    { id: 1, username: 'GondorHero', faction: 'Гондор', team: 1, is_winner: true, elo: 1420, old_rank: 8, new_rank: 6 },
    { id: 2, username: 'MordorLord', faction: 'Мордор', team: 2, is_winner: false, elo: 1390, old_rank: 7, new_rank: 9 },
  ],
};

const json = (route, payload, status = 200) => route.fulfill({
  status,
  contentType: 'application/json',
  body: JSON.stringify(payload),
});

const mockPublicApi = async (page) => {
  await page.addInitScript(() => {
    window.localStorage.setItem('token', 'test-token');
    if (!window.localStorage.getItem('language')) window.localStorage.setItem('language', 'ru');
  });

  await page.route('**/api/v1/**', async (route) => {
    const { pathname } = new URL(route.request().url());

    if (pathname === '/api/v1/auth/session') return json(route, testUser);
    if (pathname === '/api/v1/campaign/cycles/current') return json(route, {
      mechanics_version: 'legacy', cycle: null, territory_battles: [],
    });
    if (pathname === '/api/v1/users/me') return json(route, testUser);
    if (pathname === '/api/v1/admin/overview') {
      return json(route, {
        campaign: {
          status: 'offseason',
          owned_territories: 0,
          territories: 76,
          active_wars: 0,
          active_caravans: 0,
        },
        clans: { total: 0, members: 0 },
        users: { registered: 1, active: 1, blocked: 0 },
        matches: { total: 0, sync_errors: 0 },
        worker: null,
      });
    }
    if (pathname === '/api/v1/admin/clans') return json(route, { clans: [] });
    if (pathname === '/api/v1/admin/ledger') return json(route, { entries: [] });
    if (pathname === '/api/v1/admin/audit') return json(route, { entries: [] });
    if (pathname === '/api/v1/admin/feedback/tickets') return json(route, { items: [], summary: { unread: 0 } });
    if (pathname === '/api/v1/notifications/unread-count') return json(route, { unread_count: 0 });
    if (pathname === '/api/v1/notifications') return json(route, { items: [], total: 0, unread_count: 0 });
    if (pathname === '/api/v1/presence') {
      return json(route, {
        items: [{ user_id: testUser.id, is_online: true, last_seen_at: '2026-08-31T12:00:00Z' }],
        captured_at: '2026-08-31T12:00:00Z',
      });
    }
    if (pathname === '/api/v1/statistics/home') return json(route, homeSummary);
    if (pathname === '/api/v1/campaign/rules/public') return json(route, currentCampaignRules);
    if (pathname === '/api/v1/territories/stats') {
      return json(route, {
        total: 0,
        contested: 0,
        neutral: 0,
        active: 0,
        contested_percentage: 0,
        neutral_percentage: 0,
        active_percentage: 0,
      });
    }
    if (pathname === '/api/v1/territories/') return json(route, []);
    if (pathname === '/api/v1/wars/active/') return json(route, []);
    if (pathname === '/api/v1/wars/') return json(route, []);
    if (pathname === '/api/v1/wars/clan/1') return json(route, []);
    if (pathname === '/api/v1/clans/map-colors') {
      return json(route, {
        groups: [],
        blocked_colors: [],
        season_started: false,
        can_change_existing: true,
      });
    }
    if (pathname === '/api/v1/clans/') return json(route, []);
    if (pathname === '/api/v1/clans/diplomacy') return json(route, []);
    if (pathname === '/api/v1/clans/market/offers') return json(route, { offers: [], clan_activity: [], caravans: [] });
    if (pathname === '/api/v1/clans/my') return json(route, { detail: 'No clan' }, 404);
    if (pathname === '/api/v1/clans/invites/') return json(route, []);
    if (pathname === `/api/v1/shop/users/${testUser.id}/items/`) return json(route, []);
    if (pathname === '/api/v1/shop/my-items/equipped/') return json(route, []);
    if (pathname === '/api/v1/shop/items/available/') return json(route, []);
    if (pathname === `/api/v1/users/player-statistics/${testUser.username}`) return json(route, {});
    if (pathname === `/api/v1/users/${testUser.username}/matches/all`) return json(route, []);
    if (pathname === '/api/v1/statistics/live') return json(route, { matches: [], updated_at: null });
    if (pathname === '/api/v1/clans/1') {
      return json(route, {
        id: 1,
        name: 'Хранители очень длинного названия клана',
        description: 'Тестовый клан для проверки адаптивной публичной страницы.',
        motto: 'За Средиземье',
        leader_id: null,
        created_at: '2026-08-09T12:00:00Z',
        territory_points: 0,
      });
    }
    if (pathname === '/api/v1/clans/1/members') return json(route, []);
    if (pathname === '/api/v1/clans/1/assets') return json(route, []);
    if (pathname === '/api/v1/clans/1/economy') return json(route, {});
    if (pathname === '/api/v1/statistics/overall') {
      return json(route, {
        total_players: 0,
        total_clans: 0,
        total_matches: 0,
        popular_factions: [],
        popular_factions_by_patch: {},
        matches_by_day: [],
      });
    }
    if (pathname === '/api/v1/statistics/players') {
      return json(route, { players: [], total_players: 0 });
    }
    if (pathname === '/api/v1/statistics/clans') return json(route, { clans: [] });
    if (pathname === '/api/v1/campaign/seasons') return json(route, { seasons: [] });
    if (pathname === '/api/v1/campaign/influence-history') return json(route, { clans: [], events: [] });
    if (pathname === '/api/v1/achievements/my-achievements/') return json(route, []);
    if (pathname === '/api/v1/achievements/my-achievements/summary/') {
      return json(route, { completed_achievements: 0, total_achievements: 0, total_points: 0, completion_percentage: 0 });
    }
    if (pathname.startsWith('/api/v1/territories/')) return json(route, { detail: 'Not found' }, 404);

    return json(route, {});
  });
};

test.beforeEach(async ({ page }) => {
  await mockPublicApi(page);
});

test('map expires the current battle link while polling is unresolved', async ({ page }) => {
  await page.clock.install();
  let delayed = false;
  let release;
  await page.route('**/api/v1/campaign/cycles/current', async route => {
    if (delayed) await new Promise(resolve => { release = resolve; });
    return json(route, { mechanics_version: 'cycle_v1', cycle: { id: 7 },
      territory_battles: delayed ? [] : [{ battle_id: 66, territory_id: 12 }] });
  });
  await page.route('**/api/v1/territories/', route => json(route, [{ id: 12, name: 'Эвендим',
    owner_clan_id: null, adjacent_territory_ids: [], is_playable: true }]));
  await page.goto('/map');
  await selectMapEvendim(page);
  const link = page.getByRole('link', { name: 'Перейти к битве #66', exact: true });
  await expect(link).toBeVisible();
  delayed = true;
  const requested = page.waitForRequest('**/api/v1/campaign/cycles/current');
  await page.clock.fastForward(60_000);
  await requested;
  try {
    await expect(link).toHaveCount(0);
  } finally { release?.(); }
  await expect(link).toHaveCount(0);
});

test('polling failure closes an already open legacy attack dialog', async ({ page }) => {
  await page.clock.install();
  let unavailable = false;
  await page.route('**/api/v1/campaign/cycles/current', route => !unavailable
    ? json(route, { mechanics_version: 'legacy', cycle: null, territory_battles: [] })
    : json(route, { detail: 'Unavailable' }, 503));
  const errors = await mockLegacyMapAttack(page);
  await page.goto('/map');
  await selectMapEvendim(page);
  await page.getByRole('button', { name: /^Атаковать ·/ }).click();
  await expect(page.locator('.war-deployment-dialog')).toBeVisible();
  unavailable = true;
  await page.clock.fastForward(60_000);
  await expect(page.locator('.war-deployment-dialog')).toHaveCount(0);
  await expect(page.getByRole('button', { name: /^Атаковать ·/ })).toHaveCount(0);
  unavailable = false;
  await page.clock.fastForward(60_000);
  await expect(page.getByRole('button', { name: /^Атаковать ·/ })).toBeVisible();
  await expect(page.locator('.war-deployment-dialog')).toHaveCount(0);
  expect(errors).toEqual([]);
});

test('legacy draft survives successful polling but submission is suspended during validation', async ({ page }) => {
  await page.clock.install();
  let delayed = false;
  let release;
  await page.route('**/api/v1/campaign/cycles/current', async route => {
    if (delayed) await new Promise(resolve => { release = resolve; });
    return json(route, { mechanics_version: 'legacy', cycle: null, territory_battles: [] });
  });
  const errors = await mockLegacyMapAttack(page);
  await page.goto('/map');
  await selectMapEvendim(page);
  await page.getByRole('button', { name: /^Атаковать ·/ }).click();
  const search = page.locator('.war-deployment-dialog').getByRole('textbox');
  await search.fill('Draft search');
  delayed = true;
  const requested = page.waitForRequest('**/api/v1/campaign/cycles/current');
  await page.clock.fastForward(60_000);
  await requested;
  try {
    await expect(search).toBeVisible();
    await expect(search).toBeDisabled();
  } finally { release?.(); }
  await expect(search).toBeEnabled();
  await expect(search).toHaveValue('Draft search');
  expect(errors).toEqual([]);
});

async function mockLegacyMapAttack(page) {
  const errors = [];
  page.on('pageerror', error => errors.push(error.message));
  await page.route('**/api/v1/territories/', route => json(route, [{ id: 12, name: 'Эвендим',
    owner_clan_id: null, required_influence: 0, required_territories: 0,
    adjacent_territory_ids: [], is_playable: true }]));
  await page.route('**/api/v1/clans/my', route => json(route, { id: 1, name: 'Clan',
    leader_id: testUser.id, territory_points: 500, territories: [], next_attack_at: null }));
  await page.route('**/api/v1/clans/1/economy', route => json(route, {}));
  await page.route('**/api/v1/clans/1/war-readiness', route => json(route, {
    candidates: [], level: { level: 1, missing: {} }, warlord_count: 0, rule_version: 1, minimum_squad_size: 1,
    attack_points: { available: 1, capacity: 1, recoveries: [] },
  }));
  return errors;
}

async function selectMapEvendim(page) {
  await expect(page.getByRole('button', { name: 'Эвендим', exact: true })).toBeAttached();
  await expect(page.locator('#map-territory-options option[value="Эвендим"]')).toHaveCount(1);
  const search = page.getByLabel('Найти территорию или клан');
  await search.fill('Эвендим');
  await search.press('Enter');
}

test('late map help response cannot disable help on a different territory', async ({ page }) => {
  await page.route('**/api/v1/territories/', route => json(route, [
    { id: 12, name: 'Эвендим', owner_clan_id: 1, is_playable: true, adjacent_territory_ids: [] },
    { id: 13, name: 'Форност', owner_clan_id: 1, is_playable: true, adjacent_territory_ids: [] },
  ]));
  await page.route('**/api/v1/campaign/cycles/current', route => json(route, { mechanics_version: 'cycle_v1', cycle: { id: 7 }, territory_battles: [] }));
  await page.route('**/api/v1/campaign/cycles/7/map', route => json(route, { cycle_id: 7, ready: true, clan_id: 1,
    can_command: true, revision: 1, help_targets: [12, 13], battles: [], dispatches: [], ambushes: [], requests: [], allied_targets: [] }));
  let release;
  const gate = new Promise(resolve => { release = resolve; });
  await page.route('**/reinforcements/requests', async route => { await gate; await json(route, { revision: 2 }); });
  await page.goto('/map');
  await selectMapEvendim(page);
  await page.getByRole('button', { name: 'Запросить помощь союзников', exact: true }).click();
  const search = page.getByLabel('Найти территорию или клан');
  await search.fill('Форност'); await search.press('Enter');
  const response = page.waitForResponse('**/reinforcements/requests'); release(); await response;
  await expect(page.getByRole('button', { name: 'Запросить помощь союзников', exact: true })).toBeEnabled();
  await expect(page.locator('.cycle-map-panel')).not.toContainText('Запрос отправлен');
});

for (const width of [390, 1440]) {
  test(`cycle map territory opens its current battle at ${width}px`, async ({ page }) => {
    await page.setViewportSize({ width, height: 1000 });
    const territory = { id: 12, name: 'Эвендим', region: 'Арнор', owner_clan_id: null,
      adjacent_territory_ids: [], is_playable: true, required_territories: 0 };
    await page.route('**/api/v1/territories/', route => json(route, [territory]));
    await page.route('**/api/v1/campaign/cycles/current', route => json(route, {
      mechanics_version: 'cycle_v1', cycle: { id: 7 }, territory_battles: [{ battle_id: 66, territory_id: 12 }],
    }));
    const battle = { id: 66, cycle_id: 7, territory_id: 12, territory_name: 'Эвендим',
      winner_clan_id: null, recalculated_winner_clan_id: null, completed_at: null,
      adjustments: [], contributions: [], sides: [
        { clan_id: 1, clan_name: 'First clan', score: '100', role: 'defense', members: [] },
        { clan_id: 2, clan_name: 'Second clan', score: '80', role: 'attack', members: [] },
        { clan_id: 3, clan_name: 'Third clan', score: '60', role: 'attack', members: [] },
      ] };
    await page.route('**/api/v1/campaign/cycles/7', route => json(route, { id: 7, number: 7, phase: 'battle' }));
    await page.route('**/api/v1/campaign/cycles/7/battles', route => json(route, { battles: [battle] }));
    await page.route('**/api/v1/campaign/cycles/7/map', route => json(route, {
      cycle_id: 7, ready: true, revision: 1, clan_id: 1, can_command: true,
      command_deadline: '2099-01-01T00:00:00Z', server_time: '2026-10-18T00:00:00Z',
      battles: [{ battle_id: 66, territory_id: 12, sides: battle.sides }],
      dispatches: [{ id: 'map-help', territory_id: 12, sent_at: '2026-10-17T20:00:00Z',
        arrives_at: '2026-10-18T20:00:00Z', interception_at: '2026-10-17T22:00:00Z', outcome: 'pending' }],
      ambushes: [], requests: [], help_targets: [12], allied_targets: [],
    }));
    await page.route('**/api/v1/campaign/cycles/battles/66', route => json(route, battle));
    await page.goto('/map');
    const region = page.locator('path.interactive-region[data-name="Эвендим"]');
    await expect(region).toBeAttached();
    await region.dispatchEvent('click');
    const link = page.getByRole('link', { name: 'Перейти к битве #66', exact: true });
    await expect(link).toBeVisible();
    await expect(link).toHaveAttribute('href', '/campaign/cycles/7?territory=12');
    await expect(page.locator('#cycle-map-layer .cycle-map-marker')).toHaveCount(1);
    await expect(page.locator('.cycle-map-panel')).toContainText('Third clan');
    await expect(page.getByRole('link', { name: 'Открыть перехват', exact: true })).toHaveAttribute('href', '/campaign/cycles/7/interception?dispatch=map-help');
    await expect(page.getByRole('button', { name: 'Запросить помощь союзников', exact: true })).toBeVisible();
    await expect(page.getByRole('button', { name: /Начать атаку|Захватить|Атаковать|Занять/ })).toHaveCount(0);
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    await page.screenshot({ path: `test-results/cycle-map-link-${width}.png`, fullPage: true });
    await link.click();
    await expect(page).toHaveURL(/\/campaign\/cycles\/7\?territory=12$/);
    await expect(page.locator('.cycle-detail')).toBeVisible();
    await expect(page.locator('.cycle-sides')).toContainText('First clan');
    await expect(page.locator('.cycle-sides')).toContainText('Second clan');
    await expect(page.locator('.cycle-sides')).toContainText('Third clan');
  });
}

test('removed petition page has no navigation or API requests', async ({ page }) => {
  const requests = [];
  page.on('request', request => {
    if (new URL(request.url()).pathname.startsWith('/api/v1/petitions')) requests.push(request.url());
  });
  await page.goto('/petitions');
  await expect(page).toHaveURL(/\/$/);
  await expect(page.locator('a[href^="/petitions"]')).toHaveCount(0);
  await expect(page.getByRole('button', { name: 'Добавить петицию' })).toHaveCount(0);
  expect(requests).toEqual([]);
});

test('clan application explains refusal and confirms pending request', async ({ page }) => {
  const applicant = { ...testUser, role: { name: 'user' } };
  await page.route('**/api/v1/auth/session', route => json(route, applicant));
  await page.route('**/api/v1/users/me', route => json(route, applicant));
  await page.route('**/api/v1/clans/my', route => json(route, { detail: 'No clan' }, 404));
  await page.route('**/api/v1/clans/11', route => json(route, {
    id: 11, name: 'Akatsuki', leader_id: 9999, member_count: 1,
    is_recruiting: true, is_admin_clan: false, level: 1, created_at: '2026-08-11T12:00:00Z',
  }));
  for (const path of ['clans/11/members', 'clans/11/assets', 'wars/clan/11']) {
    await page.route(`**/api/v1/${path}`, route => json(route, []));
  }
  let fail = true;
  await page.route('**/api/v1/clans/11/applications', route => {
    if (fail) { fail = false; return json(route, { detail: 'Клан сейчас не ведёт набор' }, 403); }
    return json(route, { id: 69, clan_id: 11, user_id: applicant.id, status: 'pending' });
  });
  await page.goto('/clans/11');
  await page.getByRole('button', { name: 'Подать заявку', exact: true }).first().click();
  const dialog = page.getByRole('dialog');
  await dialog.getByLabel('Сообщение для клана').fill('Хочу вступить');
  await dialog.getByRole('button', { name: 'Подать заявку', exact: true }).click();
  await expect(page.getByText('Клан сейчас не ведёт набор', { exact: true })).toBeVisible();
  await dialog.getByRole('button', { name: 'Подать заявку', exact: true }).click();
  await expect(dialog).toHaveCount(0);
  await expect(page.getByText('Заявка отправлена и ожидает решения главы клана.', { exact: true })).toBeVisible();
});

test('cycle clan card embeds economy tabs without loading legacy economy', async ({ page }) => {
  const clan = { id: 11, name: 'Akatsuki', leader_id: testUser.id, member_count: 1, level: 1, created_at: '2026-08-11T12:00:00Z' };
  const legacyRequests = [];
  page.on('request', request => {
    const path = new URL(request.url()).pathname;
    if (/\/clans\/11\/(assets|economy)$/.test(path) || path === '/api/v1/clans/market/offers') legacyRequests.push(request.url());
  });
  await page.route('**/api/v1/campaign/cycles/current', route => json(route, {
    mechanics_version: 'cycle_v1', cycle: { id: 7 }, territory_battles: [],
  }));
  await page.route('**/api/v1/clans/11', route => json(route, clan));
  await page.route('**/api/v1/clans/my', route => json(route, clan));
  for (const path of ['clans/11/members', 'clans/11/applications', 'wars/clan/11']) {
    await page.route(`**/api/v1/${path}`, route => json(route, []));
  }
  await page.goto('/clans/11#relics');
  await expect(page.getByRole('link', { name: 'Казна и развитие', exact: true })).toHaveCount(0);
  await expect(page.getByRole('link', { name: 'Битвы цикла', exact: true })).toHaveCount(0);
  for (const name of ['Реликвии', 'Развитие', 'Торговля']) await expect(page.getByRole('tab', { name, exact: true })).toBeVisible();
  for (const name of ['Рынок', 'Обмен']) await expect(page.getByRole('tab', { name, exact: true })).toHaveCount(0);
  await expect(page.getByRole('tab', { name: 'Реликвии клана', exact: true })).toHaveCount(0);
  await expect(page.locator('.clan-relic-select')).toHaveCount(0);
  expect(legacyRequests).toEqual([]);
});

test('clan card fails closed when campaign mode is unavailable', async ({ page }) => {
  const legacyRequests = [];
  page.on('request', request => {
    const path = new URL(request.url()).pathname;
    if (/\/clans\/1\/(assets|economy)$/.test(path) || path === '/api/v1/clans/market/offers') legacyRequests.push(path);
  });
  await page.route('**/api/v1/campaign/cycles/current', route => json(route, { detail: 'Unavailable' }, 503));
  await page.goto('/clans/1#relics');
  await expect(page.getByRole('tab', { name: 'Обзор', exact: true })).toBeVisible();
  await expect(page.getByRole('tab', { name: 'Реликвии клана', exact: true })).toHaveCount(0);
  await expect(page.getByRole('tab', { name: 'Торговля', exact: true })).toHaveCount(0);
  await expect(page.getByRole('button', { name: 'Повторить', exact: true })).toBeVisible();
  expect(legacyRequests).toEqual([]);
});

test('clan card waits for campaign mode before starting legacy data load', async ({ page }) => {
  let releaseMode;
  const mode = new Promise(resolve => { releaseMode = resolve; });
  let clanReads = 0;
  await page.route('**/api/v1/campaign/cycles/current', async route => {
    await mode;
    return json(route, { mechanics_version: 'legacy', cycle: null, territory_battles: [] });
  });
  await page.route('**/api/v1/clans/1', async route => {
    clanReads += 1;
    await mode;
    return json(route, { id: 1, name: 'Guardians', member_count: 1, level: 1, leader_id: null, created_at: '2026-08-11T12:00:00Z' });
  });
  const ownClanResponse = page.waitForResponse('**/api/v1/clans/my');
  await page.goto('/clans/1#relics');
  await ownClanResponse;
  expect(clanReads).toBe(0);
  releaseMode();
  await expect(page.getByRole('tab', { name: 'Реликвии клана', exact: true })).toBeVisible();
  expect(clanReads).toBeGreaterThan(0);
});

test('clan leader can activate a purchased relic', async ({ page }) => {
  const clan = { id: 11, name: 'Akatsuki', leader_id: testUser.id, member_count: 1, level: 1, is_recruiting: true, created_at: '2026-08-11T12:00:00Z' };
  const entry = { asset: { id: 6, key: 'white_tree', name: 'Знамя Белого Древа', bonus_type: 'gold_income_percent', bonus_value: 8, max_level: 3 }, owned: true, level: 1, active: false, loadout_locked_until: null, influence_unlocked: true };
  await page.route('**/api/v1/clans/11', route => json(route, clan));
  await page.route('**/api/v1/clans/my', route => json(route, clan));
  await page.route('**/api/v1/clans/11/assets', route => json(route, [entry]));
  for (const path of ['clans/11/members', 'clans/11/applications', 'wars/clan/11']) {
    await page.route(`**/api/v1/${path}`, route => json(route, []));
  }
  let saved = false;
  await page.route('**/api/v1/clans/11/assets/loadout', route => {
    expect(route.request().postDataJSON()).toEqual({ asset_ids: [6] });
    saved = true;
    entry.active = true;
    return json(route, { asset_ids: [6], slots: 4 });
  });
  await page.goto('/clans/11');
  await page.getByRole('tab', { name: 'Реликвии клана', exact: true }).click();
  const selectRelic = page.locator('.clan-relic-card .clan-relic-select').first();
  await expect(selectRelic).toHaveCSS('font-weight', '700');
  await expect(selectRelic).toHaveAttribute('aria-pressed', 'false');
  await selectRelic.click();
  await expect(selectRelic).toHaveAttribute('aria-pressed', 'true');
  await expect(page.locator('.clan-loadout .clan-slot.active')).toHaveCount(1);
  await page.locator('.clan-loadout-actions button').click();
  await expect.poll(() => saved).toBe(true);
  await expect(page.locator('.clan-loadout-actions button')).toBeDisabled();
  await page.screenshot({ path: test.info().outputPath('relic-activation.png'), fullPage: true });
});

test('clan leader actions stay inside the clan card', async ({ page }) => {
  const leaderClan = {
    id: 41,
    name: 'Тестовый клан владельца',
    description: 'Карточка с действиями главы клана.',
    motto: 'Держим строй',
    leader_id: testUser.id,
    member_count: 1,
    is_recruiting: true,
    level: 1,
    created_at: '2026-08-11T12:00:00Z',
    is_admin_clan: false,
  };

  const catalogueClans = [
    leaderClan,
    ...Array.from({ length: 3 }, (_, index) => ({
      ...leaderClan,
      id: 42 + index,
      name: `Тестовый клан ${index + 2}`,
      leader_id: null,
    })),
  ];
  await page.route('**/api/v1/clans/', (route) => json(route, catalogueClans));
  await page.route('**/api/v1/clans/my', (route) => json(route, leaderClan));
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto('/clans');

  const card = page.getByRole('link', { name: /Тестовый клан владельца/ });
  const deleteButton = card.getByRole('button', { name: 'Удалить клан' });
  await expect(deleteButton).toBeVisible();

  const cardBox = await card.boundingBox();
  const buttonBox = await deleteButton.boundingBox();
  const metaBox = await card.locator('.clans-prototype-card__meta').boundingBox();
  const footerBox = await card.locator('footer').boundingBox();
  const crestBox = await card.locator('.clans-prototype-card__head img, .crest-mini').boundingBox();
  const [catalogueBox, sideColumnBox] = await Promise.all([
    page.locator('.clans-prototype-grid').boundingBox(),
    page.locator('.clans-lower-grid').boundingBox(),
  ]);
  expect(buttonBox.y + buttonBox.height).toBeLessThanOrEqual(cardBox.y + cardBox.height);
  expect(cardBox.height).toBeLessThan(360);
  expect(footerBox.y - (metaBox.y + metaBox.height)).toBeLessThan(32);
  expect(crestBox.width).toBeGreaterThanOrEqual(108);
  expect(crestBox.height).toBeGreaterThanOrEqual(108);
  await expect(card.locator('.clans-prototype-card__avatar')).toHaveCSS('border-radius', '50%');
  await expect(card).toContainText('Участников');
  expect(catalogueBox.x + catalogueBox.width).toBeLessThanOrEqual(sideColumnBox.x);
  await page.setViewportSize({ width: 1201, height: 900 });
  await expect.poll(() => page.locator('.clans-prototype-grid').evaluate((grid) => (
    getComputedStyle(grid).gridTemplateColumns.split(' ').length
  ))).toBe(3);
  const influenceTableWrap = page.locator('.clans-influence-table-wrap');
  await expect.poll(() => influenceTableWrap.evaluate((wrapper) => ({
    fits: wrapper.scrollWidth <= wrapper.clientWidth,
    overflowX: getComputedStyle(wrapper).overflowX,
  }))).toEqual({ fits: true, overflowX: 'visible' });
  await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
  await page.setViewportSize({ width: 390, height: 844 });
  await expect.poll(() => influenceTableWrap.evaluate((wrapper) => wrapper.scrollWidth <= wrapper.clientWidth)).toBe(true);
  await expect(influenceTableWrap.locator('thead')).toBeVisible();
  await expect(influenceTableWrap.locator('tbody tr')).toHaveCount(catalogueClans.length);
  await expect(influenceTableWrap.locator('tbody tr').first()).toBeVisible();
  await expect.poll(() => influenceTableWrap.locator('table').evaluate((table) => (
    Math.round(table.getBoundingClientRect().height)
  ))).toBeGreaterThan(120);
  await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
  await page.screenshot({
    path: test.info().outputPath('compact-clan-card.png'),
    fullPage: true,
  });
});

test('clan header shows clan level and emphasizes management', async ({ page }) => {
  const leaderClan = {
    id: 1,
    name: 'Хранители Севера',
    description: 'Клан для проверки шапки страницы.',
    motto: 'Север помнит',
    leader_id: testUser.id,
    member_count: 1,
    level: 1,
    map_color: '#6f86a8',
    created_at: '2026-08-11T12:00:00Z',
    is_admin_clan: false,
  };

  let currentClan = leaderClan;
  await page.route('**/api/v1/clans/1', (route) => {
    if (route.request().method() === 'PUT') {
      currentClan = { ...currentClan, ...route.request().postDataJSON() };
    }
    return json(route, currentClan);
  });
  await page.route('**/api/v1/clans/my', (route) => json(route, leaderClan));
  await page.route('**/api/v1/clans/1/members', (route) => json(route, [{
    id: 1,
    clan_id: 1,
    user_id: testUser.id,
    username: testUser.username,
    nickname: testUser.nickname,
    role: 'leader',
    joined_at: '2026-08-11T12:00:00Z',
  }]));
  await page.route(`**/api/v1/users/${testUser.id}/stats?clan_id=1`, (route) => json(route, {
    elo_ratings: { ennorath: 1412, patch_202: 1288 },
    win_rate: 64,
  }));
  await page.route('**/api/v1/clans/1/applications', (route) => json(route, []));
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto('/clans/1');

  await expect(page.getByRole('heading', { name: 'Хранители Севера' })).toBeVisible();
  await expect(page.locator('.clan-copy .MuiChip-root:not(.clan-level-badge)')).toHaveCount(0);
  await expect(page.locator('.clan-level-badge')).toHaveText('Уровень клана: 1');
  await expect(page.getByRole('link', { name: 'Правила клана' })).toHaveAttribute('href', '/rules?section=getting-started');

  await page.getByRole('tab', { name: 'Игроки' }).click();
  await expect(page.getByRole('columnheader', { name: 'Elo · Ennorath' })).toBeVisible();
  await expect(page.getByRole('columnheader', { name: 'Elo · Patch 2.02' })).toBeVisible();
  await expect(page.locator('.clan-player-table tbody tr').first()).toContainText('1412');
  await expect(page.locator('.clan-player-table tbody tr').first()).toContainText('1288');
  await page.getByRole('tab', { name: 'Обзор' }).click();

  const management = page.locator('.clan-management-menu > summary');
  await expect(management).toHaveText('Управление кланом');
  const presentation = await management.evaluate((element) => {
    const styles = getComputedStyle(element);
    return {
      fontSize: Number.parseFloat(styles.fontSize),
      paddingTop: Number.parseFloat(styles.paddingTop),
      fontWeight: Number.parseInt(styles.fontWeight, 10),
    };
  });
  expect(presentation.fontSize).toBeGreaterThanOrEqual(12);
  expect(presentation.paddingTop).toBeGreaterThanOrEqual(12);
  expect(presentation.fontWeight).toBeGreaterThanOrEqual(700);

  await management.click();
  await page.getByRole('button', { name: 'Редактировать' }).click();
  const recruitingToggle = page.getByRole('switch', { name: 'Клан принимает заявки' });
  await expect(recruitingToggle).toBeChecked();
  await recruitingToggle.click();
  await page.getByRole('button', { name: 'Сохранить' }).click();
  await expect.poll(() => currentClan.is_recruiting).toBe(false);

  await page.getByRole('tab', { name: 'Торговля' }).click();
  await expect(page.getByRole('link', { name: 'Правила рынка' })).toHaveAttribute('href', '/rules?section=market');
});

test('open clan exposes a direct application action without a generic actions menu', async ({ page }) => {
  await page.goto('/clans/1');

  await expect(page.getByRole('button', { name: 'Подать заявку', exact: true })).toBeVisible();
  await expect(page.getByText('Действия', { exact: true })).toHaveCount(0);
});

test('public shell exposes the Middle-earth design tokens and local typography', async ({ page }) => {
  await page.goto('/');

  const styles = await page.evaluate(() => {
    const root = getComputedStyle(document.documentElement);
    const body = getComputedStyle(document.body);
    const heading = getComputedStyle(document.querySelector('h1'));
    return {
      canvas: root.getPropertyValue('--cw-bg-canvas').trim(),
      gold: root.getPropertyValue('--cw-gold').trim(),
      bodyFont: body.fontFamily,
      headingFont: heading.fontFamily,
    };
  });

  expect(styles.canvas).toBe('#0b0d0c');
  expect(styles.gold).toBe('#bda56d');
  expect(styles.bodyFont).toContain('Manrope');
  expect(styles.headingFont).toContain('Cinzel');
});

test('route artwork follows the prototype screen family', async ({ page }) => {
  test.setTimeout(60_000);

  for (const [route, art, asset] of [
    ['/', 'home', 'home.webp'],
    ['/map', 'map', 'map.webp'],
    ['/shop', 'shop', 'shop.webp'],
    ['/statistics', 'stats', 'stats.webp'],
    ['/ranking', 'ranking', 'ranking.webp'],
    ['/rules', 'ranking', 'ranking.webp'],
    ['/achievements', 'achievements', 'achievements.webp'],
  ]) {
    await page.goto(route);
    const shell = page.locator('.app-container');
    await expect(shell).toBeVisible({ timeout: 15_000 });
    await expect(shell).toHaveAttribute('data-route-art', art);
    await expect.poll(() => shell.evaluate((element) => (
      getComputedStyle(element, '::before').backgroundImage
    ))).toContain(`/design-prototype/${asset}`);
  }
});

test('home page uses the redesigned public shell without mobile overflow', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto('/');

  await expect(page.locator('main.cw-page-shell')).toBeVisible();
  await expect(page.locator('.home-hero')).toBeVisible();
  await expect(page.getByRole('heading', { level: 1, name: 'Война за Средиземье' })).toBeVisible();
  await expect(page.getByRole('link', { name: 'Открыть карту', exact: true })).toHaveAttribute('href', '/map');
  await expect(page.getByRole('link', { name: 'Кланы сезона', exact: true })).toHaveAttribute('href', '/clans');
  await expect(page.getByRole('link', { name: 'Правила ClanWar', exact: true })).toHaveAttribute('href', '/rules');
  await expect(page.locator('.home-section')).toHaveCount(0);
  await expect(page.getByText('Игроков', { exact: true })).toHaveCount(1);
  await expect(page.getByText('Кланов', { exact: true })).toHaveCount(1);
  await expect(page.locator('.glow')).toHaveCount(0);
  await expect(page.getByRole('heading', { level: 2, name: 'Справочник проекта' })).toHaveCount(0);

  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBe(390);
});

test('global footer exposes project support and development credit', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto('/');

  const footer = page.getByRole('contentinfo');
  const support = footer.getByRole('link', { name: 'Поддержать проект' });
  await expect(footer).toContainText('triple D');
  await expect(support).toHaveAttribute('href', 'https://pay.cloudtips.ru/p/711c6d95');
  await expect(support).toHaveAttribute('target', '_blank');
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBe(390);
});

test('home page keeps prototype destinations available when campaign summary fails', async ({ page }) => {
  await page.route('**/api/v1/statistics/home', (route) => route.fulfill({ status: 503 }));
  await page.goto('/');

  await expect(page.getByRole('alert')).toContainText('Не удалось загрузить сводку кампании');
  await expect(page.locator('.home-hero__actions').getByRole('link')).toHaveCount(3);
  await expect(page.getByRole('link', { name: 'Правила ClanWar', exact: true })).toHaveAttribute('href', '/rules');
});

test('rules page exposes the ClanWar handbook without history or mobile overflow', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto('/rules');

  await expect(page.getByRole('heading', { level: 1, name: 'Справочник мира ClanWars' })).toBeVisible();
  await expect(page.locator('.rules-page__meta')).toHaveCount(0);
  await expect(page.getByRole('tab')).toHaveCount(14);
  await expect(page.getByRole('tab', { name: /История изменений/ })).toHaveCount(0);
  await expect(page.getByRole('heading', { level: 2, name: 'История правил' })).toHaveCount(0);
  await expect(page.getByRole('tab', { name: /О проекте/ })).toHaveAttribute('aria-selected', 'true');
  await expect(page.getByRole('heading', { level: 2, name: 'Что такое ClanWars и зачем здесь карта' })).toBeVisible();

  await page.getByRole('tab', { name: /Зачёт матчей/ }).click();
  await expect(page.getByRole('heading', { level: 2, name: 'Какие матчи дают очки в войне' })).toBeVisible();
  await expect(page.locator('.rules-rejection-list > li')).toHaveCount(7);

  await page.getByRole('tab', { name: /Экономика/ }).click();
  await expect(page.getByText(/Уровни I–V дают по 8%/)).toBeVisible();
  await expect(page.getByText(/уровни VI–X — по 4%/)).toBeVisible();
  await expect(page.getByText(/Обычные земли дают примерно 40–60 золота/)).toBeVisible();

  await page.getByRole('tab', { name: /Реликвии/ }).click();
  await expect(page.getByText(/не больше четырёх купленных реликвий/)).toBeVisible();

  await page.getByRole('tab', { name: /^11 Рынок$/ }).click();
  await expect(page.getByText(/видит маршрут, стоимость доставки и время прибытия до подтверждения/)).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBe(390);

  await page.getByRole('tab', { name: /О проекте/ }).click();
  await page.screenshot({ path: test.info().outputPath('rules-handbook-mobile.png'), fullPage: true });
  await page.setViewportSize({ width: 1440, height: 900 });
  await expect(page.locator('.rules-page__layout')).toBeVisible();
  await page.screenshot({ path: test.info().outputPath('rules-handbook-desktop.png'), fullPage: true });
});

test('rules page opens a contextual handbook section directly', async ({ page }) => {
  await page.goto('/rules?section=market');

  await expect(page.getByRole('tab', { name: /^11 Рынок$/ })).toHaveAttribute('aria-selected', 'true');
  await expect(page.getByRole('heading', { level: 2, name: 'Обмен ресурсами и путь каравана' })).toBeVisible();
});

test('rules handbook keeps content parity in English and German', async ({ page }) => {
  for (const [language, heading, economyTab, removedHistoryTab, economyText, balanceText] of [
    ['en', 'ClanWars Handbook', 'Economy', 'Changelog', /Levels I–V add 8% each/, /Normal land provides about 40–60 gold/],
    ['de', 'ClanWars-Handbuch', 'Wirtschaft', 'Änderungsverlauf', /Stufen I–V geben je 8%/, /Normales Land bringt etwa 40–60 Gold/],
  ]) {
    await page.addInitScript((nextLanguage) => {
      window.localStorage.setItem('language', nextLanguage);
    }, language);
    await page.goto('/rules');
    await expect(page.getByRole('heading', { level: 1, name: heading })).toBeVisible();
    await expect(page.getByRole('tab')).toHaveCount(14);
    await expect(page.getByRole('tab', { name: removedHistoryTab })).toHaveCount(0);
    await page.getByRole('tab', { name: new RegExp(economyTab) }).click();
    await expect(page.getByText(economyText)).toBeVisible();
    await expect(page.getByText(balanceText)).toBeVisible();
  }
});

test('season archive has its own page while obsolete clan statistics redirects', async ({ page }) => {
  await page.route('**/api/v1/campaign/archives', route => json(route, { seasons: [] }));
  await page.goto('/seasons');
  await expect(page).toHaveURL('/seasons');
  await expect(page.getByRole('heading', { level: 1, name: 'Архив сезонов' })).toBeVisible();
  await expect(page.getByText('Завершённых сезонов в архиве пока нет.')).toBeVisible();

  await page.goto('/clan-statistics');
  await expect(page).toHaveURL('/ranking');
});

test('removed chronicle route returns to the home page', async ({ page }) => {
  await page.goto('/chronicle');

  await expect(page).toHaveURL('/');
  await expect(page.getByRole('heading', { level: 1, name: 'Война за Средиземье' })).toBeVisible();
});

test('battle summary localizes campaign values and fills the full score bar', async ({ page }) => {
  await page.clock.setFixedTime(new Date('2026-09-02T12:01:00Z'));
  const crest = 'data:image/svg+xml,%3Csvg xmlns="http://www.w3.org/2000/svg" width="8" height="8"%3E%3Crect width="8" height="8" fill="%23bda56d"/%3E%3C/svg%3E';
  await page.route('**/api/v1/wars/77', (route) => json(route, {
    id: 77,
    status: 'active',
    territory_id: 15,
    territory_name: 'Осгилиат',
    attacking_clan_id: 1,
    attacking_clan_name: 'Гондор',
    attacking_clan_avatar_url: crest,
    attacking_clan_map_color: '#68765c',
    defending_clan_id: 2,
    defending_clan_name: 'Мордор',
    defending_clan_avatar_url: crest,
    defending_clan_map_color: '#87453c',
    attacker_patch: 'all',
    defender_patch: 'patch_202',
    scoring_version: 'squad-v1',
    attack_route: 'land',
    tracked_matches: 1,
    required_wins: 5,
    influence_cost: 20,
    starts_at: '2026-08-29T12:00:00Z',
    ends_at: '2026-09-02T12:00:00Z',
    attacker_power: 0,
    defender_power: 0,
    clan_scores: [
      { clan_id: 1, wins: 0, losses: 0, matches: 0, points: 25 },
      { clan_id: 2, wins: 0, losses: 0, matches: 0, points: 75 },
    ],
    match_breakdown: [{
      id: 501,
      match_id: matchDetailFixture.match_id,
      played_at: matchDetailFixture.match_date,
      map_name: matchDetailFixture.map_name,
      game_mode: matchDetailFixture.game_mode,
      duration: matchDetailFixture.duration,
      patch_family: 'ennorath',
      is_counted: true,
      winner: { username: 'GondorHero', clan_name: 'Гондор', total_points: 12 },
      loser: { username: 'MordorLord', clan_name: 'Мордор', total_points: 4 },
      participants: matchDetailFixture.participants,
    }],
    side_groups: [
      { clan_id: 1, member_count: 1, members: [{ user_id: 7, username: 'GondorHero', wins: 0, losses: 0, points: 0 }] },
      { clan_id: 2, member_count: 1, members: [{ user_id: 8, username: 'MordorLord', wins: 0, losses: 0, points: 0 }] },
    ],
  }));
  await page.route('**/api/v1/territories/15', (route) => json(route, {
    id: 15,
    name: 'Осгилиат',
    status: 'contested',
    owner_clan_name: 'Мордор',
    region: 'Гондор',
    fortifications: 2,
  }));
  await page.route('**/api/v1/clans/1/assets', (route) => json(route, []));
  await page.route('**/api/v1/clans/2/assets', (route) => json(route, []));
  await page.route('**/api/v1/statistics/matches/arena-72', (route) => json(route, matchDetailFixture));

  await page.goto('/battles/77');

  await expect(page.getByRole('heading', { name: 'Полная сводка битвы' })).toBeVisible();
  await expect(page.locator('.battle-watch')).toContainText('Подводятся итоги');
  await expect(page.locator('.battle-watch')).toContainText('Ожидаем последние реплеи');
  await expect(page.locator('.crest-big img')).toHaveCount(2);
  await expect(page.getByText('Оба патча', { exact: true })).toBeVisible();
  await expect(page.getByText('Оспаривается', { exact: true })).toBeVisible();
  await expect(page.getByText(/Отряды · Сухопутная атака/)).toBeVisible();
  await expect(page.locator('.player-no')).toHaveText(['1', '1']);
  await expect(page.locator('.lineup-elo-summary')).toHaveCount(2);
  await expect(page.locator('.lineup-elo-summary').first()).toContainText('Ennorath');
  await expect(page.locator('.lineup-elo-summary').first()).toContainText('Patch 2.02');
  await expect(page.locator('.lineup-elo-summary').first()).toContainText('—');
  await expect(page.locator('.lineup-player__elo').first()).toContainText('1420');
  await expect(page.locator('.lineup-player__elo').first()).toContainText('Patch 2.02 —');
  await page.locator('.round-row').click({ position: { x: 8, y: 8 } });
  const details = page.getByRole('dialog').filter({ hasText: 'Форност' }).first();
  await expect(details).toBeVisible();
  await expect(details.getByText('Elo · Ennorath 1.7', { exact: true })).toHaveCount(2);
  await details.getByRole('button', { name: 'Закрыть' }).last().click();

  const scoreBar = page.locator('.battle-progress.big');
  await expect(scoreBar.locator('span')).toHaveCount(2);
  const [barBox, attackerBox, defenderBox] = await Promise.all([
    scoreBar.boundingBox(),
    scoreBar.locator('.battle-progress__attacker').boundingBox(),
    scoreBar.locator('.battle-progress__defender').boundingBox(),
  ]);
  expect(Math.abs(attackerBox.width + defenderBox.width - barBox.width)).toBeLessThan(1);
});

for (const admin of [true, false]) {
  test(`battle match review permissions admin=${admin}`, async ({ page }) => {
    await page.setViewportSize({ width: admin ? 1440 : 390, height: 900 });
    await page.route('**/api/v1/users/me', route => json(route, { ...testUser, role: { name: admin ? 'admin' : 'user' } }));
    await page.route('**/api/v1/auth/session', route => json(route, { ...testUser, role: { name: admin ? 'admin' : 'user' } }));
    const result = { id: 501, match_id: 'arena-72', played_at: matchDetailFixture.match_date, map_name: 'Форност', is_counted: false, rejection_reason: 'Матч слишком короткий', admin_override: null, winner: { username: 'GondorHero', total_points: 0 }, loser: { username: 'MordorLord', total_points: 0 } };
    const war = { id: 77, status: 'completed', territory_id: 15, territory_name: 'Осгилиат', attacking_clan_id: 1, attacking_clan_name: 'Гондор', defending_clan_id: 2, defending_clan_name: 'Мордор', clan_scores: [], match_breakdown: [result], side_groups: [] };
    await page.route('**/api/v1/wars/77', route => json(route, war));
    await page.route('**/api/v1/territories/15', route => json(route, { id: 15, name: 'Осгилиат' }));
    await page.route('**/api/v1/clans/*/assets', route => json(route, []));
    await page.route('**/api/v1/statistics/matches/arena-72', route => json(route, {
      ...matchDetailFixture, rating_warning: true,
      participants: matchDetailFixture.participants.map((participant, index) => ({ ...participant, elo_is_verified: index !== 0 })),
    }));
    let failed = true;
    await page.route('**/api/v1/admin/wars/77/matches/501', route => {
      const { mode, reason } = route.request().postDataJSON();
      expect(reason).toBe('Проверено администратором');
      if (failed) { failed = false; return json(route, { detail: 'Временная ошибка' }, 500); }
      result.admin_override = mode === 'automatic' ? null : mode === 'count';
      result.is_counted = mode === 'count';
      result.admin_override_reason = mode === 'automatic' ? null : reason;
      result.rejection_reason = mode === 'count' ? null : 'Матч слишком короткий';
      return json(route, war);
    });
    await page.goto('/battles/77');
    await page.locator('.round-row').click({ position: { x: 8, y: 8 } });
    const dialog = page.getByRole('dialog').first();
    await expect(dialog).toContainText('Матч слишком короткий');
    await expect(dialog).toContainText('Их Elo не подтверждён');
    await expect(dialog.getByText('Не подтверждён', { exact: true })).toBeVisible();
    if (!admin) {
      await expect(dialog.getByRole('button', { name: 'Засчитать матч', exact: true })).toHaveCount(0);
    } else {
      await expect(dialog).toContainText('не меняют владельца территории');
      for (const name of ['Засчитать матч', 'Отменить зачёт', 'Вернуть автоматический зачёт']) {
        await dialog.getByRole('button', { name, exact: true }).click();
        const form = dialog.locator('form');
        await expect(form.getByRole('button', { name, exact: true })).toBeDisabled();
        await form.getByLabel('Причина изменения (от 3 символов)').fill('Проверено администратором');
        await form.getByRole('button', { name, exact: true }).click();
        if (name === 'Засчитать матч') {
          await expect(form).toContainText('Временная ошибка');
          await form.getByRole('button', { name, exact: true }).click();
          await expect(dialog).toContainText('Матч засчитан в этой битве');
        }
        await expect(form).toHaveCount(0);
      }
      await expect(dialog).toContainText('Матч слишком короткий');
    }
    await page.screenshot({ path: test.info().outputPath(`match-review-${admin}.png`), fullPage: true });
  });
}

test('map paints allied borders blue and shows the relation key beside neighboring lands', async ({ page }) => {
  const ownTerritory = {
    id: 1,
    name: 'Эвендим',
    owner_clan_id: 1,
    owner_clan_name: 'Гондор',
    owner_clan_map_color: '#8b6c45',
    adjacent_territory_ids: [2, 3],
    is_playable: true,
    required_territories: 0,
  };
  const alliedTerritory = {
    id: 2,
    name: 'Келдуин',
    owner_clan_id: 2,
    owner_clan_name: 'Рохан',
    owner_clan_map_color: '#80553d',
    adjacent_territory_ids: [1],
    is_playable: true,
    required_territories: 0,
  };
  const neutralTerritory = {
    id: 3,
    name: 'Арнор',
    owner_clan_id: null,
    owner_clan_name: null,
    adjacent_territory_ids: [1],
    is_playable: true,
    required_territories: 0,
  };

  await page.route('**/api/v1/territories/', (route) => json(route, [
    ownTerritory,
    alliedTerritory,
    neutralTerritory,
  ]));
  await page.route('**/api/v1/clans/my', (route) => json(route, {
    id: 1,
    name: 'Гондор',
    leader_id: testUser.id,
    territory_points: 500,
    territories: [ownTerritory],
    next_attack_at: null,
  }));
  await page.route('**/api/v1/clans/1/economy', (route) => json(route, {}));
  await page.route('**/api/v1/clans/diplomacy?**', (route) => json(route, [{
    id: 11,
    status: 'allied',
    clan_low: { id: 1, name: 'Гондор', map_color: '#8b6c45' },
    clan_high: { id: 2, name: 'Рохан', map_color: '#80553d' },
    requested_by_clan_id: null,
    updated_at: '2026-08-29T12:00:00Z',
    events: [],
  }]));

  await page.setViewportSize({ width: 1600, height: 1000 });
  await page.goto('/map');

  await expect(page.getByRole('link', { name: 'Правила карты' })).toHaveAttribute('href', '/rules?section=territories');
  await page.getByLabel('Найти территорию или клан').fill('Эвендим');

  const alliedPath = page.locator('path.interactive-region[data-name="Келдуин"]');
  await expect(alliedPath).toHaveAttribute('style', /--territory-stroke:\s*#77b9ff/i);
  await expect(page.locator('.map-relation-key')).toContainText('Союзники');
  await expect(page.locator('.map-legend-panel')).toHaveCount(0);
  await expect(page.locator('.map-neighbor-list .is-allied')).toContainText('Келдуин');

  const canvasBox = await page.locator('.strategic-map-canvas').boundingBox();
  expect(canvasBox.width).toBeGreaterThan(1000);

  const neutralPath = page.locator('path.interactive-region[data-name="Арнор"]');
  const attackableFilter = page.getByLabel('Доступные для атаки');
  await expect(page.locator('path.interactive-region.campaign-target')).toHaveCount(0);
  await page.getByRole('button', { name: 'Слои карты' }).click();
  await attackableFilter.check();
  await expect(neutralPath).toHaveClass(/campaign-target/);
  await expect(alliedPath).not.toHaveClass(/campaign-target/);
  await page.getByRole('button', { name: 'Слои карты' }).click();
  await alliedPath.dispatchEvent('click');
  await expect(page.getByText('Нельзя атаковать территорию союзного клана')).toBeVisible();
});

test('canceled clan war stays in history and is not shown as an active featured battle', async ({ page }) => {
  await page.route('**/api/v1/wars/**', (route) => json(route, [{
    id: 901,
    territory_id: 77,
    territory_name: 'Осгилиат',
    attacking_clan_id: 1,
    attacking_clan_name: 'Гондор',
    defending_clan_id: 2,
    defending_clan_name: 'Расформированный клан',
    war_type: 'territory_attack',
    status: 'canceled',
    clan_scores: [],
    tracked_matches: 0,
  }]));
  await page.goto('/wars');

  await expect(page.getByRole('heading', { name: 'Сейчас нет активных битв' })).toBeVisible();
  await expect(page.locator('[data-section="featured-battle"]')).toHaveCount(0);
  await expect(page.getByRole('tab', { name: /Завершённые/ })).toContainText('1');
});

test('attackable map filter only outlines targets from the selected clan territory', async ({ page }) => {
  const westernSource = {
    id: 1,
    name: 'Эвендим',
    owner_clan_id: 1,
    owner_clan_name: 'Гондор',
    owner_clan_map_color: '#8b6c45',
    adjacent_territory_ids: [],
    is_playable: true,
    required_territories: 0,
  };
  const easternSource = {
    id: 2,
    name: 'Келдуин',
    owner_clan_id: 1,
    owner_clan_name: 'Гондор',
    owner_clan_map_color: '#8b6c45',
    adjacent_territory_ids: [3, 4],
    is_playable: true,
    required_territories: 0,
  };
  const neutralTarget = {
    id: 3,
    name: 'Арнор',
    owner_clan_id: null,
    owner_clan_name: null,
    adjacent_territory_ids: [2],
    is_playable: true,
    required_territories: 0,
    required_influence: 100,
  };
  const expensiveTarget = {
    id: 4,
    name: 'Форност',
    owner_clan_id: null,
    owner_clan_name: null,
    adjacent_territory_ids: [2],
    is_playable: true,
    required_territories: 0,
    required_influence: 600,
  };

  await page.route('**/api/v1/territories/', (route) => json(route, [
    westernSource,
    easternSource,
    neutralTarget,
    expensiveTarget,
  ]));
  await page.route('**/api/v1/clans/my', (route) => json(route, {
    id: 1,
    name: 'Гондор',
    leader_id: testUser.id,
    territory_points: 500,
    territories: [westernSource, easternSource],
    next_attack_at: null,
  }));
  await page.route('**/api/v1/clans/1/economy', (route) => json(route, {}));
  await page.route('**/api/v1/clans/diplomacy?**', (route) => json(route, []));

  await page.setViewportSize({ width: 1600, height: 1000 });
  await page.goto('/map');

  const westernPath = page.locator('path.interactive-region[data-name="Эвендим"]');
  const easternPath = page.locator('path.interactive-region[data-name="Келдуин"]');
  const targetPath = page.locator('path.interactive-region[data-name="Арнор"]');
  const expensivePath = page.locator('path.interactive-region[data-name="Форност"]');
  const outlinedTargets = page.locator('path.interactive-region.campaign-target');
  const attackableFilter = page.getByLabel('Доступные для атаки');

  await westernPath.dispatchEvent('click');
  await expect(outlinedTargets).toHaveCount(0);

  await page.getByRole('button', { name: 'Слои карты' }).click();
  await attackableFilter.check();
  await expect(targetPath).not.toHaveClass(/campaign-target/);

  await page.getByRole('button', { name: 'Слои карты' }).click();
  await easternPath.dispatchEvent('click');
  await expect(targetPath).toHaveClass(/campaign-target/);
  await expect(expensivePath).not.toHaveClass(/campaign-target/);
  await expect(outlinedTargets).toHaveCount(1);

  await targetPath.dispatchEvent('click');
  await expect(outlinedTargets).toHaveCount(0);

  await easternPath.dispatchEvent('click');
  await expect(targetPath).toHaveClass(/campaign-target/);
  await page.getByRole('button', { name: 'Слои карты' }).click();
  await attackableFilter.uncheck();
  await expect(outlinedTargets).toHaveCount(0);
});

test('battle list renders clan logos in the featured war', async ({ page }) => {
  const attackerLogo = 'data:image/svg+xml,%3Csvg xmlns="http://www.w3.org/2000/svg" width="8" height="8"%3E%3Crect width="8" height="8" fill="%23a44"/%3E%3C/svg%3E';
  const defenderLogo = 'data:image/svg+xml,%3Csvg xmlns="http://www.w3.org/2000/svg" width="8" height="8"%3E%3Crect width="8" height="8" fill="%234a4"/%3E%3C/svg%3E';
  await page.route(/\/api\/v1\/wars\/(?:\?.*)?$/, (route) => json(route, [{
    id: 88,
    status: 'active',
    territory_id: 3,
    territory_name: 'Арнор',
    attacking_clan_id: 1,
    attacking_clan_name: 'Гондор',
    attacking_clan_avatar_url: attackerLogo,
    attacking_clan_map_color: '#aa4444',
    defending_clan_id: 2,
    defending_clan_name: 'Рохан',
    defending_clan_avatar_url: defenderLogo,
    defending_clan_map_color: '#44aa44',
    war_type: 'territory_attack',
    attack_route: 'land',
    ends_at: '2026-09-02T12:00:00Z',
    clan_scores: [
      { clan_id: 1, wins: 3, losses: 1, points: 64 },
      { clan_id: 2, wins: 1, losses: 3, points: 36 },
    ],
    tracked_matches: 4,
  }]));

  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto('/battles');

  await expect(page.getByRole('link', { name: 'Как считаются войны' })).toHaveAttribute('href', '/rules?section=attacks');

  const clanLogos = page.locator('.battle-main .crest-big img');
  await expect(clanLogos).toHaveCount(2);
  await expect(clanLogos.first()).toHaveAttribute('alt', 'Гондор — логотип клана');
  await expect(page.locator('.battle-main .side-score__record')).toHaveCount(2);
  await expect(page.getByText('Разыграно влияния', { exact: true })).toHaveCount(0);
  await expect(page.locator('.battle-main')).toContainText('Победы');
  await expect(page.locator('.battle-main')).toContainText('Поражения');
  await expect(page.locator('.vs .battle-main-actions')).toBeVisible();

  const [desktopLogo, featuredCard] = await Promise.all([
    page.locator('.battle-main .crest-big').first().boundingBox(),
    page.locator('.battle-main').boundingBox(),
  ]);
  expect(desktopLogo.width).toBeGreaterThanOrEqual(148);
  expect(desktopLogo.height).toBeGreaterThanOrEqual(148);
  expect(featuredCard.height).toBeLessThan(390);
  await expect(page.locator('.wars-tabs .tab').first()).toHaveCSS('font-size', '11px');
  await page.screenshot({
    path: test.info().outputPath('featured-battle-desktop.png'),
    fullPage: true,
  });

  await page.setViewportSize({ width: 390, height: 844 });
  const mobileLogo = await page.locator('.battle-main .crest-big').first().boundingBox();
  expect(mobileLogo.width).toBeGreaterThanOrEqual(84);
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBe(390);
});

test('contested neutral territory keeps a proportional split and shows both clan emblems', async ({ page }) => {
  await page.setViewportSize({ width: 900, height: 500 });
  const attackerEmblem = 'data:image/svg+xml,%3Csvg xmlns="http://www.w3.org/2000/svg" width="8" height="8"%3E%3Ccircle cx="4" cy="4" r="4" fill="%23aa4444"/%3E%3C/svg%3E';
  const defenderEmblem = 'data:image/svg+xml,%3Csvg xmlns="http://www.w3.org/2000/svg" width="8" height="8"%3E%3Ccircle cx="4" cy="4" r="4" fill="%2344aa44"/%3E%3C/svg%3E';
  await page.route('**/api/v1/territories/', (route) => json(route, [
    {
      id: 3,
      name: 'Арнор',
      status: 'contested',
      owner_clan_id: null,
      owner_clan_name: null,
      adjacent_territory_ids: [],
      is_playable: true,
      required_territories: 0,
    },
    {
      id: 4,
      name: 'Келдуин',
      status: 'contested',
      attacking_clan_names: ['Гондор'],
      defending_clan_names: ['Рохан'],
      adjacent_territory_ids: [],
      is_playable: true,
      required_territories: 0,
    },
  ]));
  await page.route('**/api/v1/wars/active/', (route) => json(route, [{
    id: 90,
    status: 'active',
    territory_id: 3,
    source_territory_id: null,
    attacking_clan_id: 1,
    attacking_clan_name: 'Гондор',
    attacking_clan_map_emblem_url: attackerEmblem,
    attacking_clan_map_color: '#aa4444',
    defending_clan_id: 2,
    defending_clan_name: 'Рохан',
    defending_clan_map_emblem_url: defenderEmblem,
    defending_clan_map_color: '#44aa44',
    war_type: 'territory_attack',
    clan_scores: [
      { clan_id: 1, points: 64 },
      { clan_id: 2, points: 36 },
    ],
  }]));

  await page.goto('/map');

  const contestedPath = page.locator('path.interactive-region[data-name="Арнор"]');
  const staleContestedPath = page.locator('path.interactive-region[data-name="Келдуин"]');
  await expect(contestedPath).toHaveClass(/state-war/);
  await expect(staleContestedPath).not.toHaveClass(/state-war/);
  await expect(contestedPath).toHaveAttribute('data-war-attacker-share', '64');
  await expect(contestedPath).toHaveAttribute('data-war-defender-share', '36');
  await expect(contestedPath).toHaveCSS('animation-name', 'none');
  const initialFill = await contestedPath.evaluate((path) => getComputedStyle(path).fill);
  await page.waitForTimeout(2600);
  await expect.poll(() => contestedPath.evaluate((path) => getComputedStyle(path).fill)).toBe(initialFill);

  const baseGradientStops = page.locator('#territory-war-fill-90-base stop');
  await expect(baseGradientStops).toHaveCount(4);
  await expect(baseGradientStops.nth(1)).toHaveAttribute('offset', '64%');
  await expect(baseGradientStops.nth(1)).toHaveAttribute('stop-color', '#aa4444');
  await expect(baseGradientStops.nth(2)).toHaveAttribute('offset', '64%');
  await expect(baseGradientStops.nth(2)).toHaveAttribute('stop-color', '#44aa44');

  await expect(page.locator('.clan-territory-emblem__outer-ring')).toHaveCount(0);
  const warEmblems = page.locator('.clan-territory-emblem[data-war-id="90"]');
  await expect(warEmblems).toHaveCount(2);
  await expect(warEmblems.nth(0)).toHaveAttribute('data-clan-role', 'attacker');
  await expect(warEmblems.nth(1)).toHaveAttribute('data-clan-role', 'defender');
  await expect(warEmblems.nth(0).locator('.clan-territory-emblem__image')).toHaveAttribute('href', attackerEmblem);
  await expect(warEmblems.nth(1).locator('.clan-territory-emblem__image')).toHaveAttribute('href', defenderEmblem);
  expect(Number(await warEmblems.nth(0).locator('.clan-territory-emblem__image').getAttribute('width'))).toBeGreaterThanOrEqual(48);
  expect(Number(await warEmblems.nth(1).locator('.clan-territory-emblem__image').getAttribute('width'))).toBeGreaterThanOrEqual(48);
  const emblemTransforms = await warEmblems.evaluateAll((groups) => groups.map((group) => group.getAttribute('transform')));
  expect(emblemTransforms[0]).not.toBe(emblemTransforms[1]);
  await page.screenshot({
    path: test.info().outputPath('contested-territory-split.png'),
    fullPage: true,
  });

  await contestedPath.dispatchEvent('click');
  await expect(contestedPath).toHaveClass(/selected/);
  const selectedGradientStops = page.locator('#territory-war-fill-90-selected stop');
  await expect(selectedGradientStops).toHaveCount(4);
  await expect(selectedGradientStops.first()).toHaveAttribute('stop-opacity', '0.6');
  await page.getByRole('button', { name: 'Полноэкранный режим' }).click();
  await expect(page.locator('.fullscreen-territory-panel')).toBeVisible();
  await expect.poll(() => page.evaluate(() => Boolean(document.fullscreenElement))).toBe(true);
  const [panelBox, controlsBox, viewport, scrollState] = await Promise.all([
    page.locator('.fullscreen-territory-panel').boundingBox(),
    page.locator('.map-fullscreen-controls').boundingBox(),
    page.evaluate(() => ({ width: window.innerWidth, height: window.innerHeight })),
    page.evaluate(() => {
      const shell = document.querySelector('.map-fullscreen-shell');
      return {
        htmlOverflow: getComputedStyle(document.documentElement).overflow,
        bodyOverflow: getComputedStyle(document.body).overflow,
        shellFitsHorizontally: shell.scrollWidth === shell.clientWidth,
        shellFitsVertically: shell.scrollHeight === shell.clientHeight,
        panelScrollbar: getComputedStyle(document.querySelector('.fullscreen-territory-panel')).scrollbarWidth,
      };
    }),
  ]);
  expect(panelBox.x).toBeGreaterThanOrEqual(0);
  expect(panelBox.y).toBeGreaterThanOrEqual(0);
  expect(panelBox.x + panelBox.width).toBeLessThanOrEqual(viewport.width);
  expect(panelBox.y + panelBox.height).toBeLessThanOrEqual(viewport.height);
  expect(controlsBox.x).toBeGreaterThanOrEqual(0);
  expect(controlsBox.y).toBeGreaterThanOrEqual(0);
  expect(controlsBox.x + controlsBox.width).toBeLessThanOrEqual(viewport.width);
  expect(controlsBox.y + controlsBox.height).toBeLessThanOrEqual(viewport.height);
  expect(scrollState).toEqual({
    htmlOverflow: 'hidden',
    bodyOverflow: 'hidden',
    shellFitsHorizontally: true,
    shellFitsVertically: true,
    panelScrollbar: 'none',
  });

  await page.getByRole('button', { name: 'Выйти из полноэкранного режима' }).click();
  await expect.poll(() => page.evaluate(() => Boolean(document.fullscreenElement))).toBe(false);
  await expect.poll(() => page.evaluate(() => (
    document.documentElement.classList.contains('map-fullscreen-lock')
    || document.body.classList.contains('map-fullscreen-lock')
  ))).toBe(false);
});

test('account menu keeps actions compact without achievements and quests', async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto('/profile');
  const [toolbarBox, accountBox] = await Promise.all([
    page.locator('.cw-navigation__toolbar').boundingBox(),
    page.locator('.cw-navigation__account-trigger').boundingBox(),
  ]);
  expect(Math.abs(toolbarBox.height - accountBox.height)).toBeLessThan(1);
  await page.getByRole('button', { name: 'Профиль' }).click();

  const menu = page.locator('#account-navigation-menu');
  await expect(menu).toBeVisible();
  await expect(menu.getByText('Достижения', { exact: true })).toHaveCount(0);
  await expect(menu.getByText('Задания', { exact: true })).toHaveCount(0);
  await expect(menu.getByText('Правила ClanWar', { exact: true })).toBeVisible();
});

test('account trigger shows only the public Arena nickname', async ({ page }) => {
  const arenaUser = {
    ...testUser,
    username: 'fatcat~367fb5b7',
    display_name: 'fatcat',
    nickname: null,
    clan: null,
  };
  await page.route('**/api/v1/auth/session', (route) => json(route, arenaUser));
  await page.goto('/');

  const account = page.locator('.cw-navigation__account-trigger');
  await expect(account.locator('.cw-navigation__account-copy strong')).toHaveText('fatcat');
  await expect(account.locator('.cw-navigation__account-copy small')).toHaveCount(0);
  await expect(account).not.toContainText('367fb5b7');
});

test('statistics and profile URLs use the public Arena nickname', async ({ page }) => {
  const errors = [];
  page.on('pageerror', error => errors.push(error.message));
  const arenaUser = {
    ...testUser,
    id: 17,
    username: 'fatcat~367fb5b7',
    display_name: 'fatcat',
    nickname: null,
    role: { name: 'user' },
    titles: [],
  };
  await page.route('**/api/v1/users/identity-directory', (route) => json(route, {
    players: [{ ...arenaUser, aliases: ['fatcat'] }],
  }));
  await page.route('**/api/v1/statistics/players?**', (route) => json(route, {
    players: [{
      position: 1,
      username: arenaUser.username,
      elo: 1400,
      rated: true,
      matches: 4,
      wins: 3,
      losses: 1,
      win_rate: 75,
    }],
    total_players: 1,
    patch: 'ennorath',
  }));
  await page.route('**/api/v1/users/profile/*/overview', (route) => json(route, {
    user: arenaUser,
    statistics: {},
    achievements: [],
  }));
  await page.route(`**/api/v1/shop/users/${arenaUser.id}/items/`, route => json(route, []));

  await page.goto('/statistics');
  const playerLink = page.getByRole('link', { name: 'fatcat', exact: true }).first();
  await expect(playerLink).toHaveAttribute('href', '/profile/fatcat');
  await expect(page.locator('body')).not.toContainText('367fb5b7');

  await page.goto('/profile/fatcat~367fb5b7');
  await expect(page).toHaveURL(/\/profile\/fatcat$/);
  await expect(page.locator('#profileUsername')).toContainText('fatcat', { timeout: 15_000 });
  await expect(page.locator('body')).not.toContainText('367fb5b7');
  expect(errors).toEqual([]);
});

test('top patch switch changes the ranking pool and persists the choice', async ({ page }) => {
  const requestedPatches = [];
  await page.route('**/api/v1/statistics/players?**', (route) => {
    const patch = new URL(route.request().url()).searchParams.get('patch');
    requestedPatches.push(patch);
    return json(route, {
      players: [{
        position: 1,
        username: patch === 'patch_202' ? 'PatchPlayer' : 'EnnorathPlayer',
        elo: patch === 'patch_202' ? 1420 : 1310,
        rated: true,
        matches: 3,
        wins: 2,
        losses: 1,
        win_rate: 66.7,
      }],
      total_players: 1,
      patch,
    });
  });

  await page.goto('/ranking');
  await expect(page.getByText('EnnorathPlayer', { exact: true }).first()).toBeVisible();
  await expect(page.getByRole('link', { name: 'Все матчи', exact: true }).last()).toHaveAttribute('href', '/all-matches');
  await expect(page.getByRole('link', { name: 'История влияния', exact: true }).last()).toHaveAttribute('href', '/influence-history');
  await page.locator('.cw-patch-switch__option').filter({ hasText: 'Patch 2.02' }).click();
  await expect(page.getByText('PatchPlayer', { exact: true }).first()).toBeVisible();
  await expect(page.getByRole('columnheader', { name: 'ELO · Patch 2.02' })).toBeVisible();
  expect(requestedPatches).toContain('ennorath');
  expect(requestedPatches).toContain('patch_202');

  await page.reload();
  await expect(page.getByText('PatchPlayer', { exact: true }).first()).toBeVisible();
  await expect(page.locator('.cw-patch-switch__option.is-active')).toContainText('Patch 2.02');
});

test('match row opens full Arena details, map preview and replay action', async ({ page }) => {
  await page.route('**/api/v1/statistics/matches?**', (route) => json(route, {
    matches: [matchDetailFixture],
    total_matches: 1,
    total_pages: 1,
    current_page: 1,
    limit: 20,
  }));
  await page.route('**/api/v1/statistics/matches/arena-72', (route) => json(route, matchDetailFixture));

  await page.goto('/all-matches');
  await page.locator('.all-matches-table tbody tr').click({ position: { x: 8, y: 8 } });

  const details = page.getByRole('dialog').filter({ hasText: 'Форност' }).first();
  await expect(details).toBeVisible();
  await expect(details.getByText('GondorHero', { exact: true })).toBeVisible();
  await expect(details.getByText('MordorLord', { exact: true })).toBeVisible();
  await expect(details.getByText('Ennorath 1.7', { exact: true })).toBeVisible();
  await expect(details.getByText('9137', { exact: true })).toBeVisible();
  await expect(details.getByRole('link', { name: /Скачать replay/ })).toHaveAttribute('href', '/api/v1/statistics/matches/arena-72/replay');
  await page.screenshot({ path: test.info().outputPath('match-details-dialog.png'), fullPage: true });

  await details.getByRole('button', { name: 'Увеличить карту Форност' }).click();
  await expect(page.getByRole('dialog').last().getByRole('img', { name: 'Карта Форност' })).toBeVisible();
  await page.getByRole('dialog').last().getByRole('button', { name: 'Закрыть карту' }).click();
});

test('public profile shows real presence, sends online request and splits Elo', async ({ page }) => {
  const target = {
    id: 8,
    username: 'OfflinePlayer',
    language: 'ru',
    level: 3,
    experience: 120,
    is_claimed: true,
    is_active: true,
    created_at: '2026-08-01T12:00:00Z',
    role: { name: 'user' },
    titles: [],
  };
  let onlineRequestSent = false;
  await page.route('**/api/v1/users/profile/OfflinePlayer/overview', (route) => json(route, {
    user: target,
    statistics: {
      total_matches: 4,
      wins: 2,
      losses: 2,
      win_rate: 50,
      current_elo: { ennorath: 1210, patch_202: 1375 },
      elo_history: {
        ennorath: [{ elo: 1200 }, { elo: 1210 }],
        patch_202: [{ elo: 1350 }, { elo: 1375 }],
      },
      recent_matches: [{
        match_id: matchDetailFixture.match_id,
        date: '31.08.2026',
        opponent: 'MordorLord',
        player_faction: 'Гондор',
        opponent_faction: 'Мордор',
        map: 'Форност',
        result: 'win',
        game_mode: '1v1',
        elo: 1420,
        rating_patch_family: 'ennorath',
      }],
    },
    achievements: [],
  }));
  await page.route('**/api/v1/presence?**', (route) => json(route, {
    items: [{ user_id: target.id, is_online: false, last_seen_at: new Date(Date.now() - 120_000).toISOString() }],
    captured_at: new Date().toISOString(),
  }));
  await page.route('**/api/v1/presence/8/online-request', (route) => {
    onlineRequestSent = true;
    return json(route, {
      target_user_id: 8,
      status: 'requested',
      is_online: false,
      last_seen_at: new Date(Date.now() - 120_000).toISOString(),
      cooldown_seconds: 60,
    });
  });
  await page.route('**/api/v1/shop/users/8/items/', (route) => json(route, []));
  await page.route('**/api/v1/users/8/clan', (route) => json(route, {
    id: 3,
    name: 'Стражи профиля',
    description: 'Проверка роли главы',
    leader_id: target.id,
    member_rank: 'Глава клана',
    joined_at: '2026-08-05T12:00:00Z',
    is_trader: false,
    is_warlord: false,
    created_at: '2026-08-01T12:00:00Z',
  }));
  await page.route('**/api/v1/statistics/matches/arena-72', (route) => json(route, matchDetailFixture));

  await page.goto('/profile/OfflinePlayer');
  await expect(page.getByText(/Был\(а\)/)).toBeVisible();
  await expect(page.getByRole('button', { name: 'Стражи профиля · Глава' })).toBeVisible();
  await expect(page.getByText('ELO · Ennorath', { exact: true })).toBeVisible();
  await expect(page.getByText('ELO · Patch 2.02', { exact: true })).toBeVisible();
  await page.locator('.profile-match-table tbody tr').first().click();
  const details = page.getByRole('dialog').filter({ hasText: 'Форност' }).first();
  await expect(details).toBeVisible();
  await details.getByRole('button', { name: 'Закрыть' }).last().click();
  await page.getByRole('button', { name: 'Запросить online' }).click();
  await expect(page.getByText('Запрос отправлен.', { exact: true })).toBeVisible();
  expect(onlineRequestSent).toBe(true);
});

test('balance control stays hidden for a regular user', async ({ page }) => {
  await page.route('**/api/v1/users/me', (route) => json(route, {
    ...testUser,
    username: 'layout-player',
    nickname: 'Layout Player',
    role: { name: 'user' },
  }));

  await page.goto('/profile');
  await expect(page.getByRole('button', { name: 'Изменить баланс' })).toHaveCount(0);
});

test('profile exposes prototype tabs, settings dialog and clan creation flow', async ({ page }) => {
  await page.goto('/profile');

  const avatarUpload = page.locator('.profile-hero__avatar-column .avatar-upload-btn').first();
  await expect(avatarUpload).toBeVisible();
  await expect(avatarUpload.locator('.avatar-upload-icon')).toBeVisible();
  await expect(avatarUpload.locator('img')).toHaveCount(0);

  for (const tab of ['Обзор', 'Матчи', 'Статистика', 'Достижения', 'Реликвии', 'Территории', 'Приглашения в кланы', 'Задания']) {
    await expect(page.getByRole('tab', { name: tab, exact: true })).toBeVisible();
  }
  await expect(page.getByRole('tab', { name: 'Обзор', exact: true })).toHaveCSS('font-size', '12px');
  await expect(page.locator('.profile-xp__heading')).toHaveCSS('font-size', '16px');
  await expect(page.locator('.profile-xp > small')).toHaveCSS('font-size', '11px');

  await page.getByRole('button', { name: 'Настройки', exact: true }).click();
  const settingsDialog = page.getByRole('dialog', { name: 'Настройки профиля' });
  await expect(settingsDialog).toBeVisible();
  await expect(settingsDialog.getByLabel('Язык интерфейса')).toBeVisible();
  await settingsDialog.getByRole('button', { name: 'Отмена' }).click();

  await page.getByRole('button', { name: 'Создать клан', exact: true }).click();
  const clanDialog = page.getByRole('dialog', { name: /Создание клана/ });
  await expect(clanDialog).toBeVisible();
  await expect(clanDialog.getByText('Основные сведения')).toBeVisible();
});

test('profile action menu keeps ClanWar rules after compacting secondary actions', async ({ page }) => {
  await page.goto('/profile');
  await page.getByRole('button', { name: 'Профиль', exact: true }).click();

  const menu = page.locator('#account-navigation-menu');
  const rules = menu.getByRole('menuitem', { name: 'Правила ClanWar', exact: true });
  await expect(menu.getByRole('menuitem', { name: 'Достижения', exact: true })).toHaveCount(0);
  await expect(menu.getByRole('menuitem', { name: 'Задания', exact: true })).toHaveCount(0);
  await expect(rules).toBeVisible();

  await rules.click();
  await expect(page).toHaveURL(/\/rules$/);
  await expect(page.getByRole('heading', { level: 1, name: 'Справочник мира ClanWars' })).toBeVisible();
});

test('profile quests use the campaign visual system and keep both schedules accessible', async ({ page }) => {
  const quest = (id, titleKey, descriptionKey, target, progress, rewards) => ({
    quest: {
      id,
      title_key: titleKey,
      title: titleKey,
      description_key: descriptionKey,
      description: descriptionKey,
      reward_coins: rewards[0],
      reward_experience: rewards[1],
      target_value: target,
    },
    user_quest: {
      current_progress: progress,
      is_completed: false,
      is_claimed: false,
      expires_at: '2099-08-30T12:00:00Z',
    },
    progress_percentage: Math.round((progress / target) * 100),
  });

  await page.route('**/api/v1/quests/daily?**', (route) => json(route, [
    quest(1, 'quest_daily_first_win', 'quest_daily_first_win_desc', 1, 0, [100, 50]),
    quest(2, 'quest_daily_winner', 'quest_daily_winner_desc', 5, 3, [500, 200]),
  ]));
  await page.route('**/api/v1/quests/weekly?**', (route) => json(route, [
    quest(3, 'quest_weekly_winner', 'quest_weekly_winner_desc', 10, 7, [900, 400]),
  ]));

  await page.goto('/profile');
  await page.getByRole('tab', { name: 'Задания', exact: true }).click();

  const quests = page.locator('.quests-section');
  const dailyPanel = quests.locator('#quests-daily-panel');
  await expect(quests.getByRole('tab', { name: 'Ежедневные' })).toHaveAttribute('aria-selected', 'true');
  await expect(quests.locator('.quest-tab__icon')).toHaveCount(2);
  await expect(quests.locator('.quest-tab img')).toHaveCount(0);
  await expect(dailyPanel.locator('.quest-card')).toHaveCount(2);
  await expect(dailyPanel.locator('.quest-reward-icon')).toHaveCount(4);
  await expect(dailyPanel.locator('.reward-item img')).toHaveCount(0);
  await expect(dailyPanel.getByText('Первая победа дня')).toBeVisible();
  await expect(dailyPanel.locator('.quest-timer')).toHaveCount(2);

  const weeklyTab = quests.locator('#quests-weekly-tab');
  await expect(weeklyTab).toBeVisible();
  await weeklyTab.click();
  const weeklyPanel = quests.locator('#quests-weekly-panel');
  await expect(weeklyTab).toHaveAttribute('aria-selected', 'true');
  await expect(weeklyPanel.locator('.quest-card')).toHaveCount(1);
  await expect(weeklyPanel.getByText('Победитель недели')).toBeVisible();
});

test('prototype notification control opens the real empty event feed', async ({ page }) => {
  await page.goto('/profile');

  await page.getByRole('button', { name: 'Уведомления' }).click();
  const notifications = page.getByRole('menu', { name: 'Уведомления' });
  await expect(notifications).toBeVisible();
  await expect(notifications).toContainText('Новых событий пока нет');
  await expect(notifications).toContainText('Здесь появятся приглашения, решения по заявкам, покупки и награды');
  await expect(notifications.getByRole('button')).toHaveCount(0);
});

test('notification badge refreshes when the window regains focus', async ({ page }) => {
  let unreadCount = 0;
  let requests = 0;
  await page.route('**/api/v1/notifications/unread-count', (route) => {
    requests += 1;
    return json(route, { unread_count: unreadCount });
  });

  await page.goto('/profile');
  await expect.poll(() => requests).toBeGreaterThan(0);
  await expect(page.locator('.cw-navigation__notification-dot')).toHaveCount(0);

  unreadCount = 2;
  await page.evaluate(() => window.dispatchEvent(new Event('focus')));

  await expect(page.locator('.cw-navigation__notification-dot')).toHaveText('2');
});

test('notification feed shows unread events and marks one as read', async ({ page }) => {
  let markedId = null;
  await page.route('**/api/v1/notifications/unread-count', (route) => json(route, { unread_count: 1 }));
  await page.route(/\/api\/v1\/notifications(?:\?.*)?$/, (route) => json(route, {
    items: [{
      id: 73,
      notification_type: 'clan_invite',
      title: 'Приглашение в клан «Хранители»',
      message: 'Арагорн приглашает вас присоединиться к клану.',
      link_url: '/profile',
      created_at: '2026-08-26T11:00:00Z',
      read_at: null,
    }],
    total: 1,
    unread_count: 1,
  }));
  await page.route('**/api/v1/notifications/73/read', (route) => {
    markedId = 73;
    return json(route, {
      id: 73,
      notification_type: 'clan_invite',
      title: 'Приглашение в клан «Хранители»',
      message: 'Арагорн приглашает вас присоединиться к клану.',
      link_url: '/profile',
      created_at: '2026-08-26T11:00:00Z',
      read_at: '2026-08-26T12:00:00Z',
    });
  });

  await page.goto('/profile');
  await page.getByRole('button', { name: /Уведомления: 1 непрочитанных/ }).click();
  await page.getByRole('menuitem', { name: /Приглашение в клан «Хранители»/ }).click();

  expect(markedId).toBe(73);
  await expect(page.getByRole('button', { name: 'Уведомления' })).toBeVisible();
});

test('notification feed localizes Russian server events in English and German', async ({ page }) => {
  await page.route('**/api/v1/notifications/unread-count', (route) => json(route, { unread_count: 1 }));
  await page.route(/\/api\/v1\/notifications(?:\?.*)?$/, (route) => json(route, {
    items: [{
      id: 74,
      notification_type: 'clan_invite',
      title: 'Приглашение в клан «Хранители»',
      message: 'Арагорн приглашает вас присоединиться к клану.',
      link_url: '/profile',
      created_at: '2026-08-26T11:00:00Z',
      read_at: null,
    }],
    total: 1,
    unread_count: 1,
  }));

  for (const locale of [
    { code: 'en', title: 'Clan invitation', message: 'Open the linked section for details.' },
    { code: 'de', title: 'Clan-Einladung', message: 'Öffne den verknüpften Bereich für Details.' },
  ]) {
    await page.goto('/');
    await page.evaluate((language) => window.localStorage.setItem('language', language), locale.code);
    await page.goto('/profile');
    await page.locator('.cw-navigation__notifications-trigger').click();
    const menu = page.locator('#notifications-menu');
    await expect(menu).toContainText(locale.title);
    await expect(menu).toContainText(locale.message);
    await expect(menu).not.toContainText('Приглашение');
    await expect(menu).not.toContainText('приглашает');
    await page.keyboard.press('Escape');
  }
});

test('admin shell matches prototype navigation and opens real catalogue editors', async ({ page }) => {
  const overview = {
    users: { registered: 12, blocked: 1 },
    clans: { total: 4, members: 21 },
    campaign: { territories: 76, owned_territories: 18, active_wars: 2, active_caravans: 1 },
    matches: { total: 240, sync_errors: 0 },
    worker: null,
  };
  const relic = {
    id: 501,
    name: 'Кольцо дозорного',
    description: 'Редкая реликвия для профиля.',
    price: 900,
    item_type: 'relic',
    rarity: 'rare',
    category: 'relic',
    slot: 'relic',
    image_url: null,
    css_class: null,
    is_available: true,
    created_at: '2026-08-20T12:00:00Z',
  };
  await page.route('**/api/v1/admin/overview', (route) => json(route, overview));
  await page.route('**/api/v1/admin/clans', (route) => json(route, { clans: [] }));
  await page.route('**/api/v1/admin/ledger**', (route) => json(route, { entries: [] }));
  await page.route('**/api/v1/admin/audit**', (route) => json(route, { entries: [] }));
  await page.route('**/api/v1/shop/items/**', (route) => json(route, [relic]));
  await page.route('**/api/v1/achievements/**', (route) => json(route, []));

  await page.setViewportSize({ width: 1440, height: 960 });
  await page.goto('/admin');

  await expect(page.locator('.cw-navigation')).toBeHidden();
  await expect(page.getByRole('tab', { name: 'Реликвии' })).toBeVisible();
  await page.getByRole('tab', { name: 'Реликвии' }).click();
  await expect(
    page.getByRole('row').filter({ hasText: 'Кольцо дозорного' }).getByRole('cell').first(),
  ).toBeVisible();
  await page.getByRole('button', { name: 'Добавить реликвию' }).click();
  const relicDialog = page.getByRole('dialog', { name: /Добавить реликвию/ });
  await expect(relicDialog.getByLabel('Название')).toBeVisible();
  await relicDialog.getByRole('button', { name: 'Отмена' }).click();

  await page.getByRole('tab', { name: 'Достижения' }).click();
  await page.getByRole('button', { name: 'Новое достижение' }).first().click();
  const achievementDialog = page.getByRole('dialog', { name: /Новое достижение/ });
  await expect(achievementDialog.getByText(/Текущий API хранит один текст/)).toBeVisible();
  await achievementDialog.locator('.MuiDialogActions-root button').first().click();

  await page.setViewportSize({ width: 390, height: 844 });
  await expect(page.locator('.admin-tabs')).not.toHaveClass(/MuiTabs-vertical/);
  await expect(page.getByRole('tab', { selected: true })).toBeVisible();
});

test('account routes share login, registration and honest recovery tabs', async ({ page }) => {
  await page.route('**/api/v1/auth/password-recovery/request', (route) => json(route, {
    accepted: true,
    message: 'Если аккаунт с таким адресом существует, письмо со ссылкой уже отправлено.',
  }));

  await page.goto('/login');
  await expect(page.getByRole('tab', { name: 'Вход' })).toBeVisible();
  await page.getByRole('tab', { name: 'Регистрация' }).click();
  await expect(page.getByRole('heading', { name: 'Создать героя' })).toBeVisible();
  await page.getByRole('tab', { name: 'Восстановление' }).click();
  await expect(page.getByRole('heading', { name: 'Восстановление доступа' })).toBeVisible();
  await page.getByLabel('Email').fill('hero@example.com');
  await page.getByRole('button', { name: 'Отправить ссылку' }).click();
  await expect(page.getByText(/Если аккаунт с таким адресом существует/)).toBeVisible();
});

test('feedback page submits context and keeps the support thread visible', async ({ page }) => {
  let submittedBody = '';
  const ticket = {
    id: 91,
    reference: 'CW-000091',
    reporter_id: testUser.id,
    reporter_name: testUser.username,
    assigned_admin_id: null,
    assigned_admin_name: null,
    category: 'bug',
    title: 'Реликвия перекрывает карточку',
    description: 'Изображение выходит за границы превью и закрывает описание.',
    reproduction_steps: 'Открыть клан и перейти в реликвии.',
    expected_result: 'Изображение внутри превью.',
    actual_result: 'Изображение перекрывает текст.',
    attachment_url: null,
    source_path: '/clans/1',
    user_agent: 'Playwright',
    status: 'new',
    priority: 'normal',
    admin_unread: true,
    created_at: '2026-08-30T10:00:00Z',
    updated_at: '2026-08-30T10:00:00Z',
    resolved_at: null,
    messages: [],
  };
  let tickets = [];
  await page.route('**/api/v1/feedback/tickets', async (route) => {
    if (route.request().method() === 'POST') {
      submittedBody = route.request().postData() || '';
      tickets = [ticket];
      return json(route, ticket, 201);
    }
    return json(route, tickets);
  });

  await page.setViewportSize({ width: 1280, height: 900 });
  await page.goto('/feedback?from=%2Fclans%2F1');
  await page.getByLabel('Краткая тема').fill(ticket.title);
  await page.getByLabel('Подробное описание').fill(ticket.description);
  await page.getByLabel('Шаги воспроизведения').fill(ticket.reproduction_steps);
  await page.getByLabel('Фактический результат').fill(ticket.actual_result);
  await page.getByRole('button', { name: 'Отправить обращение' }).click();

  await expect(page.getByText('CW-000091').first()).toBeVisible();
  await expect(page.getByRole('heading', { name: ticket.title })).toBeVisible();
  expect(submittedBody).toContain('/clans/1');
  expect(submittedBody).not.toContain('must-not-be-stored');
  await page.screenshot({ path: test.info().outputPath('feedback-thread.png'), fullPage: true });
});

test('admin feedback queue and balance simulator expose operational controls', async ({ page }) => {
  const overview = {
    users: { registered: 12, blocked: 1, active: 11 },
    clans: { total: 4, members: 21 },
    campaign: { territories: 76, owned_territories: 18, active_wars: 0, active_caravans: 1 },
    matches: { total: 240, sync_errors: 0 },
    worker: null,
  };
  const ticket = {
    id: 91, reference: 'CW-000091', reporter_id: 8, reporter_name: 'Ranger',
    assigned_admin_id: null, assigned_admin_name: null, category: 'bug',
    title: 'Кнопка не отвечает', description: 'После нажатия ничего не происходит.',
    reproduction_steps: 'Открыть карту и нажать кнопку.', expected_result: 'Открывается окно.',
    actual_result: 'Ничего не происходит.', attachment_url: null, source_path: '/map',
    user_agent: 'Vivaldi', status: 'new', priority: 'critical', admin_unread: true,
    created_at: '2026-08-30T10:00:00Z', updated_at: '2026-08-30T10:00:00Z', resolved_at: null, messages: [],
  };
  const report = {
    rule_set: { id: 2, version: 7 }, horizon_days: 30,
    inputs: {
      starting_resources: { gold: 500, iron: 10, wood: 10, food: 5, mithril: 2, influence: 100 },
      territories: [
        { id: 1, name: 'Арнор', region: 'eriador', resource_type: 'wood', resource_output: 1, resource_wealth: 80, influence_value: 25, required_influence: 30, stronghold_power: 0, has_port: true, is_coastal: true, adjacent_territory_ids: [2], svg_path_data: 'M0 0' },
        { id: 2, name: 'Форност', region: 'eriador', resource_type: 'iron', resource_output: 1, resource_wealth: 90, influence_value: 30, required_influence: 30, stronghold_power: 0, has_port: true, is_coastal: true, adjacent_territory_ids: [1], svg_path_data: 'M1 1' },
      ],
    },
    scenarios: [{
      id: 'new:normal:balanced', profile: 'new', pace: 'normal', strategy: 'balanced',
      parameters: { capture_interval_days: 8 }, purchases: [], checkpoints: { '7': { territory_count: 2, influence: 120, clan_level: 1, total_development_levels: 1, relic_levels: 0 } },
      final: { territory_count: 4, influence: 240, clan_level: 2, total_development_levels: 6, relic_levels: 1, resources: { gold: 600, iron: 15, wood: 18, food: 9, mithril: 2 }, accumulated: { gold: 900, iron: 20, wood: 20, food: 10, mithril: 2 }, spent: { gold: 800, iron: 15, wood: 12, food: 5, mithril: 1 } },
    }],
    signals: [{ code: 'first_upgrade_slow', scenario_id: 'new:normal:balanced', detail: 'Первое улучшение приобретается слишком поздно.', parameter: 'POPULATION_BASE_GOLD_COST', current_value: 500, proposed_value: 450 }],
    recommendations: [{ signal: 'first_upgrade_slow' }],
  };
  const sandboxReport = {
    rule_set: { id: 2, version: 7 }, catalog: { territories: report.inputs.territories },
    economy: {
      scenario: {
        parameters: { days: 30, active_members: 12, capture_interval_days: 5, strategy: 'balanced' },
        initial_territory_ids: [1], final_territory_ids: [1, 2], captured_territory_ids: [2],
        timeline: [{ day: 0, resources: { gold: 500 } }, { day: 30, resources: { gold: 720 } }],
        captures: [{ territory_id: 2, territory_name: 'Форност', day: 5 }], purchases: [],
        final: { territory_count: 2, influence: 155, total_development_levels: 3, resources: { gold: 720, iron: 18, wood: 16, food: 8, mithril: 2 } },
      },
      baseline: { final: {}, timeline: [{ day: 0, resources: { gold: 500 } }, { day: 30, resources: { gold: 680 } }] },
      delta_from_current_rules: { resources: { gold: 40, iron: 0, wood: 0, food: 0, mithril: 0 }, territories: 0, development_levels: 0 },
    },
    war: { possible: true, map: { source_id: 1, target_id: 2, route_ids: [1, 2] } },
    trade: { possible: true, map: { source_id: 1, target_id: 2, route_ids: [1, 2] } },
  };
  await page.route('**/api/v1/admin/overview', (route) => json(route, overview));
  await page.route('**/api/v1/admin/clans', (route) => json(route, { clans: [] }));
  await page.route('**/api/v1/admin/ledger**', (route) => json(route, { entries: [] }));
  await page.route('**/api/v1/admin/audit**', (route) => json(route, { entries: [] }));
  await page.route('**/api/v1/admin/feedback/tickets**', (route) => json(route, { items: [ticket], total: 1, summary: { total: 1, unread: 1, new: 1, in_progress: 0, critical: 1 } }));
  await page.route('**/api/v1/admin/balance-simulator**', (route) => json(route, route.request().method() === 'POST' ? sandboxReport : report));

  await page.setViewportSize({ width: 1440, height: 960 });
  await page.goto('/admin?section=feedback&ticket=91');
  await expect(page.getByRole('heading', { name: 'Обращения пользователей' })).toBeVisible();
  await expect(page.getByText('Кнопка не отвечает').first()).toBeVisible();
  await expect(page.getByText('Непрочитано')).toBeVisible();

  await page.getByRole('tab', { name: /Симулятор/ }).click();
  await expect(page.getByRole('heading', { name: 'Симулятор баланса' })).toBeVisible();
  await expect(page.getByText('Как читать результат')).toBeVisible();
  await page.getByRole('button', { name: 'Смоделировать все три блока' }).click();
  await expect(page.getByRole('heading', { name: 'Экономика через 30 дней' })).toBeVisible();
  await page.screenshot({ path: test.info().outputPath('admin-balance-sandbox.png'), fullPage: true });
  await page.setViewportSize({ width: 390, height: 844 });
  await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
  await page.screenshot({ path: test.info().outputPath('admin-balance-sandbox-mobile.png'), fullPage: true });
  await page.setViewportSize({ width: 1440, height: 960 });
  await page.getByRole('tab', { name: /Автопроверка 36 профилей/ }).click();
  await expect(page.getByText('first_upgrade_slow')).toBeVisible();
  await page.screenshot({ path: test.info().outputPath('admin-balance-simulator.png'), fullPage: true });
});

test('clan relic artwork stays inside its preview and never covers the body', async ({ page }) => {
  const clan = {
    id: 1, name: 'Хранители', description: 'Тестовый клан.', motto: 'Храним север',
    leader_id: null, member_count: 0, level: 2, map_color: '#6f86a8',
    created_at: '2026-08-11T12:00:00Z', is_admin_clan: false,
  };
  const assets = ['white_tree', 'granite_bastion', 'mithril_pickaxe', 'tower_guard'].map((key, index) => ({
    asset: {
      id: index + 1, key, name: `Реликвия ${index + 1}`, description: 'Описание',
      bonus_type: 'defense_power', bonus_value: 2, max_level: 3,
      gold_cost: 100, iron_cost: 0, wood_cost: 0, food_cost: 0, mithril_cost: 0,
    },
    owned: false, level: 0, active: false, influence_unlocked: true,
    next_costs: { gold: 700, iron: 0, wood: 0, food: 0, mithril: 0 },
  }));
  await page.route('**/api/v1/clans/1', (route) => json(route, clan));
  await page.route('**/api/v1/clans/my', (route) => json(route, clan));
  await page.route('**/api/v1/clans/1/members', (route) => json(route, []));
  await page.route('**/api/v1/clans/1/assets', (route) => json(route, assets));
  await page.route('**/api/v1/clans/1/economy', (route) => json(route, {}));
  await page.route('**/api/v1/wars/clan/1', (route) => json(route, []));
  await page.route('**/api/v1/clans/market/offers**', (route) => json(route, { offers: [], caravans: [] }));
  await page.route('**/api/v1/territories/', (route) => json(route, []));

  await page.setViewportSize({ width: 1440, height: 960 });
  await page.goto('/clans/1');
  const sectionTabs = page.locator('.clan-section-tabs [role="tab"]');
  await expect(sectionTabs).toHaveCount(7);
  await sectionTabs.nth(4).click();
  const card = page.locator('.clan-relic-grid > .clan-relic-card').first();
  await expect(card).toBeVisible();
  const art = page.locator('.clan-relic-grid > .clan-relic-card .clan-relic-art').first();
  const image = page.locator('.clan-relic-grid > .clan-relic-card .clan-relic-art img').first();
  const body = page.locator('.clan-relic-grid > .clan-relic-card .clan-relic-body').first();
  await expect(art).toBeVisible();
  await expect(image).toBeVisible();
  await expect(body).toBeVisible();
  await expect(card.locator('.clan-relic-price strong')).toContainText('700');
  const artBox = await art.boundingBox();
  const imageBox = await image.boundingBox();
  const bodyBox = await body.boundingBox();
  expect(imageBox.y).toBeGreaterThanOrEqual(artBox.y - 1);
  expect(imageBox.y + imageBox.height).toBeLessThanOrEqual(artBox.y + artBox.height + 1);
  expect(artBox.y + artBox.height).toBeLessThanOrEqual(bodyBox.y + 1);
  await page.screenshot({ path: test.info().outputPath('contained-clan-relics.png'), fullPage: true });
});

test('site theme is purchased in the shop and enabled from inventory', async ({ page }) => {
  const themes = [
    {
      id: 101,
      name: 'Пепел Мордора',
      description: 'Тёмная вулканическая тема с алыми акцентами и пепельным фоном.',
      price: 150,
      item_type: 'site_theme',
      rarity: 'rare',
      css_class: 'theme-mordor',
      slot: 'site_theme',
      category: 'site_theme',
      is_available: true,
      created_at: '2026-08-14T12:00:00Z',
    },
    {
      id: 102,
      name: 'Страж Гондора',
      description: 'Холодный камень, серебро и золото Белого Древа.',
      price: 275,
      item_type: 'site_theme',
      rarity: 'epic',
      css_class: 'theme-gondor',
      slot: 'site_theme',
      category: 'site_theme',
      is_available: true,
      created_at: '2026-08-14T12:00:00Z',
    },
    {
      id: 103,
      name: 'Рамка Retro Paint',
      description: 'Оригинальная рамка Paint из сохранённого Steam-профиля поверх аватара.',
      price: 120,
      item_type: 'avatar_frame',
      rarity: 'rare',
      css_class: 'avatar-frame-palantir',
      slot: 'avatar_frame',
      category: 'avatar_frame',
      is_available: true,
      created_at: '2026-08-14T12:00:00Z',
    },
    {
      id: 104,
      name: 'Летний аниме-фон',
      description: 'Оригинальный анимированный фон из сохранённого Steam-профиля.',
      price: 180,
      item_type: 'profile_background',
      rarity: 'epic',
      css_class: 'profile-background-starlight',
      slot: 'profile_background',
      category: 'profile_background',
      is_available: true,
      created_at: '2026-08-14T12:00:00Z',
    },
    {
      id: 105,
      name: 'Печать следопыта',
      description: 'Реликвия для оформления карточки статистики.',
      price: 90,
      item_type: 'stat_card_style',
      rarity: 'uncommon',
      css_class: 'stat-card-ranger',
      slot: 'stat_card_style',
      category: 'stat_card_style',
      is_available: true,
      created_at: '2026-08-14T12:00:00Z',
    },
  ];
  let inventory = [];

  await page.route('**/api/v1/shop/items/available/', (route) => json(route, themes));
  await page.route(`**/api/v1/shop/users/${testUser.id}/items/`, (route) => json(route, inventory));
  await page.route('**/api/v1/shop/my-items/equipped/', (route) => (
    json(route, inventory.filter((userItem) => userItem.is_equipped))
  ));
  await page.route('**/api/v1/shop/purchase/', (route) => {
    const { item_id: itemId } = route.request().postDataJSON();
    const item = themes.find((candidate) => candidate.id === itemId);
    const userItem = {
      id: 501,
      user_id: testUser.id,
      item_id: item.id,
      is_equipped: false,
      purchased_at: '2026-08-14T12:05:00Z',
      item,
    };
    inventory = [userItem];
    return json(route, { user_item: userItem, new_balance: 850, item_price: item.price });
  });
  await page.route('**/api/v1/shop/equip/', (route) => {
    const { user_item_id: userItemId } = route.request().postDataJSON();
    inventory = inventory.map((userItem) => ({
      ...userItem,
      is_equipped: userItem.id === userItemId,
    }));
    return json(route, inventory.find((userItem) => userItem.id === userItemId));
  });

  await page.goto('/shop');
  const mordorShopCard = page.locator('.shop-item-card').filter({ hasText: 'Пепел Мордора' });
  await expect(mordorShopCard.getByRole('img', { name: 'Пепел Мордора' })).toBeVisible();
  await expect(page.getByRole('img', { name: 'Рамка Retro Paint' })).toBeVisible();
  await expect(page.getByRole('img', { name: 'Летний аниме-фон' })).toBeVisible();
  await expect(page.getByRole('img', { name: 'Печать следопыта' })).toHaveAttribute(
    'src',
    '/design-prototype/relic_9.webp',
  );
  await mordorShopCard.getByRole('button', { name: 'Подробнее' }).click();
  const detailsDialog = page.getByRole('dialog', { name: /Пепел Мордора/ });
  await expect(detailsDialog).toBeVisible();
  await detailsDialog.getByRole('button', { name: 'Купить' }).click();
  const purchaseDialog = page.getByRole('dialog', { name: 'Подтверждение покупки' });
  await expect(purchaseDialog).toContainText('Пепел Мордора');
  await purchaseDialog.getByRole('button', { name: 'Подтвердить покупку' }).click();

  await page.getByRole('tab', { name: /Моя коллекция/ }).click();
  const inventoryCard = page.locator('.inventory-item').filter({ hasText: 'Пепел Мордора' });
  await inventoryCard.getByRole('button', { name: 'Подробнее' }).click();
  await page.getByRole('dialog', { name: /Пепел Мордора/ }).getByRole('button', { name: 'Экипировать' }).click();

  await expect(page.locator('html')).toHaveAttribute('data-site-theme', 'theme-mordor');
  await expect.poll(() => page.evaluate(() => (
    getComputedStyle(document.documentElement).getPropertyValue('--primary-color').trim()
  ))).toBe('#ff5a4f');
  await expect(inventoryCard).toHaveClass(/equipped/);
  await expect(inventoryCard.locator('.owned')).toHaveText('Экипировано');

  inventory = [
    ...inventory,
    {
      id: 502,
      user_id: testUser.id,
      item_id: themes[2].id,
      is_equipped: true,
      purchased_at: '2026-08-14T12:06:00Z',
      item: themes[2],
    },
    {
      id: 503,
      user_id: testUser.id,
      item_id: themes[3].id,
      is_equipped: true,
      purchased_at: '2026-08-14T12:07:00Z',
      item: themes[3],
    },
  ];
  await page.goto('/profile');
  await expect(page.locator('.avatar-container')).toHaveClass(/avatar-frame-palantir/);
  await expect(page.locator('.app-container')).toHaveClass(/profile-background-starlight/);
  const backgroundVideo = page.locator('.profile-background-starlight-video');
  await expect(backgroundVideo).toHaveAttribute(
    'poster',
    '/cosmetics/steam-profile-background-poster.jpg'
  );
  await expect(page.locator('.profile-background-starlight-video source[type="video/webm"]')).toHaveAttribute(
    'src',
    '/cosmetics/steam-profile-background.webm'
  );
  await expect(page.locator('.profile-background-starlight-video source[type="video/mp4"]')).toHaveAttribute(
    'src',
    '/cosmetics/steam-profile-background.mp4'
  );
  await expect.poll(() => page.locator('.avatar-container').evaluate((element) => (
    getComputedStyle(element, '::before').backgroundImage
  ))).toContain('/cosmetics/steam-profile-avatar-frame.png');
  await expect(page.locator('.avatar-container .avatar-upload-btn')).toHaveCount(0);
  await expect(page.getByRole('button', { name: 'Сменить аватар' })).toBeVisible();
  const originalVideoNode = await backgroundVideo.elementHandle();
  await page.waitForTimeout(500);
  expect(await originalVideoNode.evaluate((element) => element.isConnected)).toBe(true);
  await expect.poll(() => page.locator('.profile-header-card').evaluate((element) => (
    getComputedStyle(element).backgroundColor
  ))).toContain('0.74');
  await page.getByRole('tab', { name: 'Реликвии', exact: true }).click();
  await expect(page.locator('.profile-tab-heading')).toContainText('Коллекция реликвий');
  await expect(page.locator('.inventory-item').filter({ hasText: 'Пепел Мордора' })).toBeVisible();
});

test('profile cosmetics follow the viewed player inventory', async ({ page }) => {
  const frameItem = {
    id: 201,
    name: 'Рамка Retro Paint',
    description: 'Оригинальная рамка Paint.',
    price: 120,
    item_type: 'avatar_frame',
    rarity: 'rare',
    css_class: 'avatar-frame-palantir',
    slot: 'avatar_frame',
    category: 'avatar_frame',
    is_available: true,
    created_at: '2026-08-14T12:00:00Z',
  };
  const backgroundItem = {
    id: 202,
    name: 'Летний аниме-фон',
    description: 'Оригинальный анимированный фон.',
    price: 180,
    item_type: 'profile_background',
    rarity: 'epic',
    css_class: 'profile-background-starlight',
    slot: 'profile_background',
    category: 'profile_background',
    is_available: true,
    created_at: '2026-08-14T12:00:00Z',
  };
  const owner = { ...testUser, id: 8, username: 'paint-owner', nickname: 'Paint Owner' };
  const plain = { ...testUser, id: 9, username: 'plain-player', nickname: 'Plain Player' };
  const overview = (user) => ({ user, statistics: null, achievements: [] });
  const equipped = [frameItem, backgroundItem].map((item, index) => ({
    id: 601 + index,
    user_id: owner.id,
    item_id: item.id,
    is_equipped: true,
    purchased_at: '2026-08-14T12:05:00Z',
    item,
  }));

  await page.route('**/api/v1/users/profile/paint-owner/overview', (route) => json(route, overview(owner)));
  await page.route('**/api/v1/users/profile/plain-player/overview', (route) => json(route, overview(plain)));
  await page.route(`**/api/v1/shop/users/${owner.id}/items/`, (route) => json(route, equipped));
  await page.route(`**/api/v1/shop/users/${plain.id}/items/`, (route) => json(route, []));
  await page.route('**/api/v1/users/paint-owner/matches/all', (route) => json(route, []));
  await page.route('**/api/v1/users/plain-player/matches/all', (route) => json(route, []));

  await page.goto('/profile/paint-owner');
  await expect(page.locator('.avatar-container')).toHaveClass(/avatar-frame-palantir/);
  await expect(page.locator('.app-container')).toHaveClass(/profile-background-starlight/);
  await expect(page.locator('.profile-background-starlight-video')).toHaveCount(1);

  await page.goto('/profile/plain-player');
  await expect(page.locator('#profileUsername')).toContainText('plain-player');
  await expect(page.locator('.avatar-container')).not.toHaveClass(/avatar-frame-palantir/);
  await expect(page.locator('.app-container')).not.toHaveClass(/profile-background-starlight/);
  await expect(page.locator('.profile-background-starlight-video')).toHaveCount(0);
});

test('mobile navigation matches the prototype and keeps profile in the menu', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto('/');

  const brand = page.getByRole('link', { name: 'BFME ClanWars' });
  const menuButton = page.getByRole('button', { name: 'Открыть меню' });
  const languageButton = page.getByRole('button', { name: 'Язык' });
  const accountButton = page.locator('.cw-navigation__account-trigger');

  await expect(brand).toBeVisible();
  await expect(menuButton).toBeVisible();
  await expect(languageButton).toBeVisible();
  await expect(accountButton).toBeHidden();
  await expect(page.locator('header.cw-navigation')).toHaveCSS('position', 'sticky');

  expect(await brand.evaluate((element) => element.scrollWidth <= element.clientWidth)).toBe(true);
  await expect(languageButton.getByText('RU', { exact: true })).toBeHidden();

  const boxes = await Promise.all([
    brand.boundingBox(),
    menuButton.boundingBox(),
    languageButton.boundingBox(),
  ]);
  boxes.forEach((box) => {
    expect(box).not.toBeNull();
  });
  boxes.slice(1).forEach((box) => {
    expect(box.width).toBeGreaterThanOrEqual(40);
    expect(box.height).toBeGreaterThanOrEqual(40);
  });
  boxes.slice(0, -1).forEach((box, index) => {
    expect(box.x + box.width).toBeLessThanOrEqual(boxes[index + 1].x);
  });

  await menuButton.click();
  const mobileMenu = page.getByRole('menu').filter({
    has: page.getByRole('menuitem', { name: 'Главная' }),
  });
  await expect(mobileMenu).toBeVisible();
  const mobileMenuBox = await mobileMenu.boundingBox();
  expect(mobileMenuBox.x + mobileMenuBox.width).toBeLessThanOrEqual(390);

  for (const label of [
    'Главная',
    'Кланы',
    'Общая статистика',
    'Статистика кланов',
    'Все матчи',
    'История влияния',
    'Архив сезонов',
    'Битвы',
    'Карта',
    'Профиль',
    'Админ-панель',
  ]) {
    await expect(page.getByRole('menuitem', { name: label, exact: true })).toBeVisible();
  }

  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBe(390);
});

test('desktop navigation matches the prototype primary destinations', async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto('/');

  await expect(page.locator('header.cw-navigation')).toBeVisible();
  await expect(page.getByRole('link', { name: 'BFME ClanWars' })).toHaveAttribute('aria-current', 'page');
  await expect(page.getByRole('button', { name: 'Открыть меню' })).toBeHidden();
  await expect(page.getByRole('link', { name: 'Кланы', exact: true })).toBeVisible();
  await expect(page.getByRole('link', { name: 'Битвы', exact: true })).toBeVisible();
  await expect(page.getByRole('link', { name: 'Карта', exact: true })).toBeVisible();
  await expect(page.getByRole('link', { name: 'Рейтинг', exact: true })).toBeVisible();
  await expect(page.getByRole('link', { name: 'Статистика', exact: true })).toHaveAttribute('href', '/statistics');
  await expect(page.getByRole('link', { name: 'Магазин', exact: true })).toBeVisible();

  await page.getByRole('button', { name: 'Язык' }).click();
  const languageMenu = page.locator('#language-menu');
  await expect(languageMenu).toBeVisible();
  await expect(languageMenu.locator('.cw-language-flag')).toHaveCount(3);
});

test('map territory links to its ongoing battle', async ({ page }) => {
  await page.route('**/api/v1/territories/', (route) => json(route, [{ id: 3, name: 'Арнор', owner_clan_id: null, status: 'contested', is_playable: true, adjacent_territory_ids: [] }]));
  await page.route('**/api/v1/wars/active/', (route) => json(route, [{ id: 99, territory_id: 3, territory_name: 'Арнор', status: 'active', attacking_clan_id: 1, attacking_clan_name: 'Гондор', clan_scores: [] }]));
  await page.goto('/map');
  const territory = page.getByRole('button', { name: 'Арнор', exact: true });
  await expect(territory).toHaveAttribute('tabindex', '0');
  await territory.press('Enter');
  await expect(page.getByRole('link', { name: 'Перейти к битве #99' })).toHaveAttribute('href', '/battles/99');
});

test('completed battle has admin score correction and match review controls', async ({ page }) => {
  const war = { id: 99, territory_name: 'Арнор', status: 'completed', attacking_clan_id: 1, attacking_clan_name: 'Гондор', defending_clan_id: 2, defending_clan_name: 'Мордор', attacker_patch: 'all', tracked_matches: 1, rejected_matches: 0, clan_scores: [], match_breakdown: [{ id: 1, winner: { username: 'GondorHero', total_points: 10 }, loser: { username: 'MordorLord' }, is_counted: true, admin_override: null }] };
  let adjusted = false;
  await page.route('**/api/v1/admin/wars**', async (route) => {
    const path = new URL(route.request().url()).pathname;
    if (path.endsWith('/points')) {
      const payload = route.request().postDataJSON();
      expect(payload.points).toBe(25);
      expect(payload.clan_id).toBe(2);
      expect(payload.reason).toBe('Score correction');
      expect(payload.request_id).toMatch(/^[0-9a-f-]{36}$/);
      adjusted = true;
      return json(route, { ...war, score_adjustments: [{ id: 1, clan_id: 2, points: 25, reason: payload.reason }] });
    }
    return json(route, path.endsWith('/99') ? war : { wars: [war] });
  });
  await page.goto('/admin');
  await page.getByRole('tab', { name: /Битвы|Войны/ }).click();
  await page.getByRole('button', { name: 'Открыть', exact: true }).click();
  await expect(page.getByRole('button', { name: 'Засчитать', exact: true })).toBeVisible();
  await expect(page.getByRole('button', { name: 'Исключить', exact: true })).toBeVisible();
  await page.getByRole('button', { name: 'Скорректировать очки' }).click();
  const dialog = page.getByRole('dialog').last();
  await dialog.getByRole('spinbutton').fill('25');
  await dialog.getByRole('textbox').fill('Score correction');
  await dialog.getByRole('button', { name: 'Подтвердить' }).click();
  await expect(page.getByText(/\+25 · Score correction/)).toBeVisible();
  expect(adjusted).toBe(true);
});

test('mobile territory map is visible first and opens accessible bottom details', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto('/map');

  const territory = page.locator('path.interactive-region').first();
  await expect(territory).toBeVisible({ timeout: 15_000 });
  const territoryName = await territory.getAttribute('data-name');
  const territoryBox = await territory.boundingBox();

  expect(territoryBox.x).toBeLessThan(390);
  expect(territoryBox.x + territoryBox.width).toBeGreaterThan(0);
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBe(390);
  await expect(territory).toHaveAttribute('tabindex', '0');

  await territory.focus();
  expect(await territory.evaluate((element) => getComputedStyle(element).outlineStyle)).toBe('none');
  await territory.press('Enter');

  const details = page.getByRole('dialog', { name: 'Территория' });
  await expect(details).toBeVisible();
  await expect(details.getByText(territoryName, { exact: true })).toBeVisible();
  const closeButton = details.getByRole('button', { name: 'Закрыть' });
  await expect(closeButton).toBeVisible();

  await expect.poll(() => details.evaluate(
    (element) => element.getBoundingClientRect().bottom - window.innerHeight,
  )).toBeLessThanOrEqual(0);
  await closeButton.click();
  await expect(details).toBeHidden();
  await expect(territory).toBeFocused();
  await expect(territory).toBeVisible();
});

test('desktop territory map keeps the information sidebar right of the canvas', async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto('/map');

  const sidebar = page.getByRole('complementary', { name: 'Территория' });
  const map = page.getByRole('region', { name: 'Карта' });
  await expect(sidebar).toBeVisible({ timeout: 15_000 });
  await expect(map).toBeVisible();

  const [sidebarBox, mapBox] = await Promise.all([sidebar.boundingBox(), map.boundingBox()]);
  expect(mapBox.x + mapBox.width).toBeLessThanOrEqual(sidebarBox.x);
  expect(Math.abs(sidebarBox.height - mapBox.height)).toBeLessThanOrEqual(1);

  const territory = page.locator('path.interactive-region').first();
  const territoryName = await territory.getAttribute('data-name');
  await territory.click({ force: true });
  await expect(sidebar.getByText(territoryName, { exact: true })).toBeVisible();
  await expect(page.getByRole('dialog', { name: 'Территория' })).toHaveCount(0);
});

test('tablet public shell stays responsive in Russian English and German', async ({ page }) => {
  await page.setViewportSize({ width: 768, height: 1024 });
  await page.goto('/');

  const languageButton = page.locator('button').filter({
    has: page.locator('[data-testid="LanguageIcon"]'),
  }).first();

  for (const language of [
    { code: 'en', label: 'English' },
    { code: 'de', label: 'Deutsch' },
    { code: 'ru', label: 'Русский' },
  ]) {
    await languageButton.click();
    await page.getByRole('menuitem').filter({ hasText: language.label }).click();
    await expect(page.locator('html')).toHaveAttribute('lang', language.code);
    expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBe(768);
  }

  await expect(page.getByRole('button', { name: 'Открыть меню' })).toBeVisible();
  await expect(languageButton.getByText('RU', { exact: true })).toBeVisible();

  await page.goto('/map');
  const map = page.getByRole('region', { name: 'Карта' });
  await expect(map).toBeVisible({ timeout: 15_000 });
  await expect(page.getByRole('complementary', { name: 'Территория' })).toHaveCount(0);
  const mapBox = await map.boundingBox();
  expect(mapBox.width).toBeGreaterThanOrEqual(700);
  expect(mapBox.height).toBeGreaterThanOrEqual(420);
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBe(768);
});

for (const locale of [
    {
      code: 'en',
      statistics: ['World analytics', 'Statistics', 'Map control'],
      clan: ['About the clan', 'Players', 'Trade'],
      matches: ['All matches', 'Filters', 'Player nickname'],
      shopRarity: 'Rare',
      regions: ['Europe', 'CIS'],
    },
    {
      code: 'de',
      statistics: ['Weltanalyse', 'Statistik', 'Kartenkontrolle'],
      clan: ['Über den Clan', 'Spieler', 'Handel'],
      matches: ['Alle Spiele', 'Filter', 'Spielername'],
      shopRarity: 'Selten',
      regions: ['Europa', 'GUS'],
    },
]) {
  test(`reviewed public pages render complete interface text in ${locale.code}`, async ({ page }) => {
    test.setTimeout(60000);
    await page.setViewportSize({ width: 768, height: 1024 });
    await page.addInitScript((language) => window.localStorage.setItem('language', language), locale.code);
    await page.route('**/api/v1/shop/items/available/', (route) => json(route, [{
      id: 401,
      name: 'Ranger frame',
      description: 'Profile frame',
      price: 50,
      item_type: 'avatar_frame',
      rarity: 'rare',
      slot: 'avatar_frame',
      is_available: true,
    }]));
    await page.goto('/statistics');
    await expect(page.locator('html')).toHaveAttribute('lang', locale.code);
    await expect(page.locator('.statistics-exact-page .page-title .eyebrow')).toHaveText(locale.statistics[0]);
    await expect(page.getByRole('heading', { level: 1, name: locale.statistics[1], exact: true })).toBeVisible();
    await expect(page.locator('[data-section="territory-control"] h2')).toHaveText(locale.statistics[2]);

    await page.goto('/clans/1');
    await expect(page.getByText(locale.clan[0], { exact: true })).toBeVisible();
    await expect(page.getByRole('tab', { name: locale.clan[1], exact: true })).toBeVisible();
    await expect(page.getByRole('tab', { name: locale.clan[2], exact: true })).toBeVisible();

    await page.goto('/all-matches');
    await expect(page.getByRole('heading', { level: 1, name: locale.matches[0], exact: true })).toBeVisible();
    await expect(page.getByRole('heading', { level: 2, name: locale.matches[1], exact: true })).toBeVisible();
    await expect(page.getByPlaceholder(locale.matches[2], { exact: true })).toBeVisible();

    await page.goto('/shop');
    await expect(page.locator('option[value="rare"]')).toHaveText(locale.shopRarity);
    await expect(page.locator('.shop-card .rarity').first()).toHaveText(locale.shopRarity);

    await page.goto('/register');
    await expect(page.locator('#register-region option[value="Europe"]')).toHaveText(locale.regions[0]);
    await expect(page.locator('#register-region option[value="CIS"]')).toHaveText(locale.regions[1]);
    expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBe(768);
  });
}

test('admin permanent deletion requires matching ID and reason', async ({ page }) => {
  let deleted = false;
  await page.route('**/api/v1/admin/clans', (route) => json(route, { clans: deleted ? [] : [{ id: 123, name: 'Disposable clan', members: 0, territories: 0 }] }));
  await page.route('**/api/v1/admin/clans/123', async (route) => {
    expect(route.request().method()).toBe('DELETE');
    expect(route.request().postDataJSON()).toEqual({ confirmation_id: 123, reason: 'Cleanup test' });
    deleted = true;
    await json(route, { deleted: true });
  });
  await page.goto('/admin');
  await page.getByRole('tab', { name: /Кланы/ }).click();
  await page.getByRole('button', { name: 'Удалить навсегда' }).click();
  const dialog = page.getByRole('dialog');
  const submit = dialog.getByRole('button', { name: 'Удалить навсегда' });
  await expect(submit).toBeDisabled();
  await dialog.getByLabel('Введите ID 123 для подтверждения').fill('123');
  await expect(submit).toBeDisabled();
  await dialog.getByLabel('Причина удаления').fill('Cleanup test');
  await submit.click();
  await expect(dialog).not.toBeVisible();
  await expect(page.getByText('Disposable clan', { exact: true })).toHaveCount(0);
});

test('admin dashboard renders reviewed English and German labels', async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });

  for (const locale of [
    { code: 'en', title: 'Control panel', overview: 'Overview', subtitle: 'Campaign Status and Administrative Operations' },
    { code: 'de', title: 'Bedienfeld', overview: 'Übersicht', subtitle: 'Kampagnenstatus und Verwaltungsvorgänge' },
  ]) {
    await page.goto('/');
    await page.evaluate((language) => window.localStorage.setItem('language', language), locale.code);
    await page.goto('/admin');

    await expect(page.locator('html')).toHaveAttribute('lang', locale.code);
    await expect(page.getByRole('heading', { name: locale.title, exact: true })).toBeVisible();
    await expect(page.getByRole('tab', { name: locale.overview, exact: true })).toBeVisible();
    await expect(page.getByText(locale.subtitle, { exact: true })).toBeVisible();
    expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBe(1440);
  }
});

test('public route matrix has no runtime errors or document overflow', async ({ page }) => {
  // Linux CI renders the SVG map and eight lazy routes more slowly than a
  // warmed local Chromium run; retain the full matrix with enough headroom.
  test.setTimeout(180_000);
  const runtimeErrors = [];
  page.on('pageerror', (error) => runtimeErrors.push(error.message));

  for (const viewport of [
    { width: 390, height: 844 },
    { width: 768, height: 1024 },
    { width: 1440, height: 900 },
  ]) {
    await page.setViewportSize(viewport);

    for (const route of ['/', '/clans', '/clans/1', '/battles', '/statistics', '/map', '/profile', '/shop', '/ranking', '/achievements']) {
      runtimeErrors.length = 0;
      await page.goto(route);
      await page.waitForTimeout(300);

      expect(runtimeErrors, `${route} at ${viewport.width}px`).toEqual([]);
      const documentWidth = await page.evaluate(() => ({
        scrollWidth: document.documentElement.scrollWidth,
        innerWidth: window.innerWidth,
      }));
      expect(documentWidth.scrollWidth, `${route} at ${viewport.width}px`).toBe(documentWidth.innerWidth);
    }
  }
});


for (const [language, label, warPhrase, conquestPhrase] of [
  ['ru', 'Уровень клана: 3', 'Боевой период длится 60 часов', 'уменьшаются вдвое с округлением вниз'],
  ['en', 'Clan level: 3', 'The battle period lasts 60 hours', 'attack 6 → 3, defence 8 → 4'],
  ['de', 'Clanstufe: 3', 'Die Kampfzeit beträgt 60 Stunden', 'Angriff 6 → 3, Verteidigung 8 → 4'],
]) {
  for (const width of [390, 1440]) {
    test(`requirements 79-83 show clan level and new rules in ${language} at ${width}px`, async ({ page }) => {
      await page.setViewportSize({ width, height: 900 });
      await page.addInitScript((selected) => window.localStorage.setItem('language', selected), language);
      const clan = {
        id: 1, name: 'Guardians', motto: 'For Middle-earth', level: 3,
        leader_id: null, created_at: '2026-08-09T12:00:00Z',
        territory_points: 230, member_count: 17, territory_count: 4, map_color: '#6f86a8',
      };
      await page.route('**/api/v1/clans/', (route) => json(route, [clan]));
      await page.route('**/api/v1/clans/1', (route) => json(route, clan));
      await page.goto('/clans');
      await expect(page.locator('.clans-prototype-card__level')).toHaveText(label);
      await expect(page.locator('.clans-prototype-card__level')).toBeVisible();
      expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBe(width);
      await page.screenshot({ path: test.info().outputPath('clan-list-level.png'), fullPage: true });
      await page.getByRole('link', { name: /Guardians/ }).click();
      await expect(page.locator('.clan-level-badge')).toHaveText(label);
      await expect(page.locator('.clan-level-badge')).toBeVisible();
      const levelFontSize = await page.locator('.clan-level-badge').evaluate(
        (element) => Number.parseFloat(getComputedStyle(element).fontSize),
      );
      expect(levelFontSize).toBeGreaterThanOrEqual(15);
      expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBe(width);
      await page.screenshot({ path: test.info().outputPath('clan-header-level.png'), fullPage: true });
      await page.goto('/rules?section=war-result');
      await expect(page.getByText(warPhrase, { exact: false })).toBeVisible();
      await page.goto('/rules?section=war-result');
      await expect(page.getByText(conquestPhrase, { exact: false })).toBeVisible();
      expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBe(width);
    });
  }
}
