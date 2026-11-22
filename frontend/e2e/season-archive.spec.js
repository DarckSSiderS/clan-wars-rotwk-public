import { expect, test } from '@playwright/test';
import { readFileSync } from 'node:fs';

const map = readFileSync(new URL('../public/map.svg', import.meta.url));
const season = { id: 1, number: 1, name: 'Тестовый сезон', starts_at: '2026-08-31T00:00:00Z', ends_at: '2026-11-01T09:00:00Z' };
const payload = {
  season, schema_version: 1, captured_at: season.ends_at, view_box: '0 0 3570.6 2339.7',
  map_image_url: '/api/v1/campaign/archives/1/map.svg',
  territories: [
    { id: 3, name: 'Старый Арнор', region: 'arnor', owner_clan_id: 7, svg_path_data: 'M800 500h800v600H800Z', is_playable: true, has_port: true, stronghold_power: 3, fortifications: 4, offense_level: 2 },
    { id: 4, name: 'Старый Форност', region: 'arnor', owner_clan_id: null, svg_path_data: 'M1600 500h700v500H1600Z', is_playable: true },
  ],
  clans: [
    { clan_id: 8, clan_name: 'Бывший соперник', clan_map_color: '#d66079', rank: 2, influence: 9999, territory_count: 0, wars_won: 2, awards: [] },
    { clan_id: 7, clan_name: 'Старые хранители', clan_map_color: '#42bfc4', rank: 1, influence: 1234, territory_count: 1, wars_won: 7,
      awards: [{ key: 'season_champion', image: '/assets/awards/clan/season-champion.png', label_key: 'clan_award_season_champion', description_key: 'clan_award_season_description' }] },
  ],
};

async function isolate(page, { list = { seasons: [season] }, status = 200, detail = payload, signedIn = false } = {}) {
  const requests = [];
  const errors = [];
  page.on('pageerror', error => errors.push(error.message));
  await page.addInitScript(() => localStorage.setItem('language', 'ru'));
  await page.route('**/api/**', async route => {
    const request = route.request();
    const path = new URL(request.url()).pathname;
    requests.push({ path, method: request.method(), headers: request.headers() });
    if (path === '/api/v1/campaign/archives/1/map.svg') return route.fulfill({ contentType: 'image/svg+xml', body: map });
    if (path === '/api/v1/campaign/archives') return route.fulfill({ json: list });
    if (path === '/api/v1/campaign/archives/1') return route.fulfill({ status, json: detail });
    if (!signedIn) return route.fulfill({ status: 401, json: {} });
    let json = {};
    if (path.endsWith('/auth/session') || path.endsWith('/users/me')) json = { id: 1, username: 'Глава', language: 'ru', is_verified: true, is_claimed: true, role: { name: 'user' }, onboarding_completed: true };
    else if (path.endsWith('/campaign/cycles/current')) json = { mechanics_version: 'legacy', cycle: null, territory_battles: [], interseason: true, archived_season_id: 1 };
    else if (path === '/api/v1/territories/') json = payload.territories.map((item, index) => ({ ...item, name: ['Арнор', 'Форност'][index] }));
    else if (path === '/api/v1/clans/') json = [{ id: 7, name: 'Новое имя', map_color: '#ff0000' }];
    else if (path.endsWith('/clans/my')) json = { id: 7, name: 'Новое имя', leader_id: 1 };
    else if (path.endsWith('/wars/active/')) json = [];
    else if (path.includes('notifications')) json = { items: [], unread_count: 0, total: 0 };
    else if (path.includes('presence')) json = { items: [] };
    else if (path.includes('localization') || path.includes('diplomacy')) json = [];
    return route.fulfill({ json });
  });
  return { requests, errors };
}

test('anonymous list opens frozen map, clan standings and saved awards without live API', async ({ page }) => {
  const { requests, errors } = await isolate(page);
  await page.goto('/seasons');
  await page.getByRole('link', { name: /Тестовый сезон/ }).click();
  await expect(page).toHaveURL(/\/seasons\/1$/);
  const svg = page.locator('svg.season-archive-map');
  await expect(svg).toHaveAttribute('viewBox', payload.view_box);
  await expect(svg.locator('image')).toHaveAttribute('href', payload.map_image_url);
  const territory = page.getByRole('button', { name: 'Старый Арнор', exact: true });
  await expect(territory).toHaveAttribute('d', payload.territories[0].svg_path_data);
  await expect(territory).toHaveAttribute('fill', '#42bfc4');
  await territory.focus();
  await page.keyboard.press('Enter');
  const sidebar = page.getByRole('complementary', { name: 'Сведения архива' });
  await expect(sidebar).toContainText('Старый Арнор');
  await expect(sidebar).toContainText('Старые хранители');
  await expect(sidebar.getByText('Чемпион сезона', { exact: true })).toBeVisible();
  await expect.poll(() => sidebar.locator('img').first().evaluate(img => img.complete && img.naturalWidth > 0)).toBe(true);
  await expect(page.locator('.season-archive-table tbody tr').first()).toContainText('Старые хранители');
  await page.getByRole('button', { name: 'Увеличить', exact: true }).click();
  await expect(svg).not.toHaveAttribute('viewBox', payload.view_box);
  const zoomedView = await svg.getAttribute('viewBox');
  await svg.focus();
  await page.keyboard.press('ArrowRight');
  await expect(svg).not.toHaveAttribute('viewBox', zoomedView);
  await page.getByRole('button', { name: 'Сбросить вид', exact: true }).click();
  await expect(svg).toHaveAttribute('viewBox', payload.view_box);
  await page.getByRole('button', { name: 'Бывший соперник', exact: true }).first().click();
  await expect(sidebar).toContainText('Бывший соперник');
  await expect(sidebar).toContainText('Нет сохранённых наград');
  await page.getByRole('button', { name: 'Старый Форност', exact: true }).press('Space');
  await expect(sidebar).toContainText('Нейтральная земля');
  await page.getByLabel('Территория', { exact: true }).selectOption('3');
  await page.evaluate(() => window.scrollTo(0, 0));
  await page.screenshot({ path: 'test-results/season-archive/desktop.png', fullPage: true });
  expect(requests.filter(row => row.path.startsWith('/api/v1/campaign/archives')).every(row => row.method === 'GET' && !row.headers.authorization)).toBe(true);
  expect(requests.filter(row => /\/territories|\/clans|\/wars|\/cycles/.test(row.path))).toEqual([]);
  expect(errors).toEqual([]);
});

test('unsupported snapshots do not fall back to a live map', async ({ page }) => {
  const { requests } = await isolate(page, { detail: { ...payload, schema_version: 99 } });
  await page.goto('/seasons/1');
  await expect(page.getByRole('alert')).toContainText('Не удалось загрузить архив');
  await expect(page.locator('svg.season-archive-map')).toHaveCount(0);
  expect(requests.filter(row => /\/territories|\/clans|\/wars|\/cycles/.test(row.path))).toEqual([]);
});

test('empty list, missing archive and recoverable error are explicit', async ({ page }) => {
  await isolate(page, { list: { seasons: [] }, status: 404 });
  await page.goto('/seasons');
  await expect(page.getByText('Завершённых сезонов в архиве пока нет.')).toBeVisible();
  await page.goto('/seasons/1');
  await expect(page.getByRole('alert')).toContainText('Архив сезона не найден');
  await page.route('**/api/v1/campaign/archives/1', route => route.fulfill({ status: 503, json: {} }));
  await page.reload();
  await expect(page.getByRole('alert')).toContainText('Не удалось загрузить архив');
  await page.route('**/api/v1/campaign/archives/1', route => route.fulfill({ json: payload }));
  await page.getByRole('button', { name: 'Повторить', exact: true }).click();
  await expect(page.locator('svg.season-archive-map')).toBeVisible();
});

test('mobile stays within viewport and language changes do not rename frozen entities', async ({ page }) => {
  await isolate(page);
  await page.setViewportSize({ width: 390, height: 844 });
  await page.addInitScript(() => localStorage.setItem('language', 'en'));
  await page.goto('/seasons/1');
  await expect(page.getByRole('heading', { name: 'Тестовый сезон', exact: true })).toBeVisible();
  await expect(page.getByRole('heading', { name: 'Final standings' })).toBeVisible();
  await page.getByLabel('Territory', { exact: true }).selectOption('3');
  await expect(page.locator('.season-archive-sidebar')).toContainText('Старый Арнор');
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await page.evaluate(() => window.scrollTo(0, 0));
  await page.screenshot({ path: 'test-results/season-archive/mobile.png', fullPage: true });
});

test('completed legacy season map exposes archive without attack, reinforcement or upgrade mutations', async ({ page }) => {
  const { requests } = await isolate(page, { signedIn: true });
  await page.goto('/map');
  await expect(page.getByRole('status').filter({ hasText: 'Сезон завершён' })).toBeVisible();
  await expect(page.getByRole('link', { name: 'Архив сезонов', exact: true }).first()).toHaveAttribute('href', '/seasons');
  const territory = page.getByRole('button', { name: 'Форност', exact: true });
  await expect(territory).toHaveAttribute('tabindex', '0');
  await territory.press('Enter');
  await expect(page.getByRole('button', { name: /Атаковать|Подкреплен|подкреплен|Управление территорией|Параметры территории/ })).toHaveCount(0);
  await expect(page.getByRole('dialog')).toHaveCount(0);
  await expect(page.locator('.cycle-map-panel')).toHaveCount(0);
  expect(requests.filter(row => !['GET', 'HEAD'].includes(row.method))).toEqual([]);
});

test('full frozen geometry renders at desktop scale with regional awards', async ({ page }) => {
  const source = readFileSync(new URL('../public/map-interactive.svg', import.meta.url), 'utf8');
  const territories = await page.evaluate(svg => {
    const doc = new DOMParser().parseFromString(svg, 'image/svg+xml');
    return [...doc.querySelectorAll('path[data-name]')].map((path, index) => ({
      id: index + 100, name: path.getAttribute('data-name'), region: path.getAttribute('data-region'),
      svg_path_data: path.getAttribute('d'), owner_clan_id: index % 3 === 0 ? null : index % 2 ? 7 : 8,
      is_playable: true, has_port: index % 4 === 0, stronghold_power: 3, development_level: 2, influence_value: 15,
    }));
  }, source);
  const detail = structuredClone(payload);
  detail.territories = territories;
  detail.clans[1].awards.push({ key: 'region-arnor', image: '/assets/awards/clan/region-arnor.png', label_key: 'clan_award_arnor', description_key: 'clan_award_regional_description' });
  await isolate(page, { detail });
  await page.goto('/seasons/1');
  await expect(page.locator('.season-archive-territory')).toHaveCount(territories.length);
  const selected = territories.find(item => item.owner_clan_id === 7);
  await page.getByLabel('Территория', { exact: true }).selectOption(String(selected.id));
  const sidebar = page.locator('.season-archive-sidebar');
  await expect(sidebar).toContainText('Уровень развития');
  await expect(sidebar).toContainText('15');
  expect(territories.length).toBeGreaterThan(70);
  await page.evaluate(() => window.scrollTo(0, 0));
  await page.screenshot({ path: 'test-results/season-archive/full-map-desktop.png', fullPage: true });
});
