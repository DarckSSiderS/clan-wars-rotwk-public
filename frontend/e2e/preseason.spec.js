import { test, expect } from '@playwright/test';

const relicKeys = ['royal_charter', 'war_foundry', 'mithril_standard', 'granite_bastion', 'merchant_guild', 'white_tree', 'red_arrow', 'iron_crown', 'palantir', 'dwarf_anvil', 'ents_seed', 'mordor_forge', 'helms_horn', 'ring_of_barahir', 'galadhrim_mirror'];
async function setup(page, options = {}) {
  const data = { open: true, preparation_id: 1, clan_id: 7, clan_name: 'Akatsuki', revision: 4,
    is_head: true, can_choose_lands: true, can_choose_relics: true, land_status: 'pending',
    selected_lands: [], selected_relics: [], initial_owned: [10], eligibility: { eligible: true }, slot: null,
    treasury: { gold: '1000', iron: '30', wood: '30', food: '20', mithril: '5' },
    territories: [
      { id: 10, name: 'Home', region: 'Rohan', owner_clan_id: null, selection_owner_clan_id: 7, neighbours: [11] },
      { id: 11, name: 'North', region: 'Rohan', owner_clan_id: null, selection_owner_clan_id: null, neighbours: [10, 12] },
      { id: 12, name: 'East', region: 'Rohan', owner_clan_id: null, selection_owner_clan_id: null, neighbours: [11] },
      { id: 13, name: 'Reserved', owner_clan_id: null, selection_owner_clan_id: 8, neighbours: [] },
      { id: 14, name: 'Port', has_port: true, selection_owner_clan_id: null, neighbours: [] },
      { id: 15, name: 'Fortress', fortress: 3, selection_owner_clan_id: null, neighbours: [] },
      { id: 16, name: 'Island', selection_owner_clan_id: null, neighbours: [] },
    ], relics: relicKeys.map((key, i) => ({ key, name: `Реликвия ${i + 1}`, effect: 'influence', effects: ['15', '25', '35'] })), ...options.context };
  const commands = [], requests = [];
  await page.addInitScript(language => localStorage.setItem('language', language), options.language || 'ru');
  await page.route('**/api/v1/**', async route => {
    const path = new URL(route.request().url()).pathname;
    requests.push(path);
    let payload = {};
    if (path.endsWith('/auth/session') || path.endsWith('/users/me')) payload = { id: 1, username: 'Head', language: 'ru', is_claimed: true, is_verified: true, role: { name: 'user' }, onboarding_completed: true };
    else if (path.endsWith('/clans/my')) payload = options.clanless ? null : { id: 7 };
    else if (path.endsWith('/preseason/status')) payload = { open: options.open ?? true, preparation_id: 1 };
    else if (path === '/api/v1/campaign/preseason/clans/7') payload = data;
    else if (path.includes('/preseason/clans/7/')) {
      const body = route.request().postDataJSON(); commands.push({ path, body });
      if (options.conflict) { data.can_choose_lands = false; data.revision = 5; return route.fulfill({ status: 409, json: { detail: 'Revision conflict' } }); }
      if (path.endsWith('/preview')) payload = { selected: body.selected, release: [16] };
      else {
        if (options.gate) await options.gate;
        if (path.endsWith('/lands')) { data.selected_lands = body.selected; data.can_choose_lands = false; data.land_status = 'claimed'; }
        else { data.selected_relics = body.selected; data.can_choose_relics = false; }
        data.revision++; payload = data;
      }
    } else if (path.includes('notifications')) payload = { items: [], unread_count: 0, total: 0 };
    else if (path.includes('presence')) payload = { items: [] };
    else if (path.includes('localization') || path.includes('diplomacy')) payload = [];
    return route.fulfill({ json: payload });
  });
  await page.goto(options.url || '/preseason');
  return { data, commands, requests };
}

test('closed status never loads private context or offers choices', async ({ page }) => {
  const { requests } = await setup(page, { open: false });
  await expect(page.getByText('Предсезонный выбор закрыт.', { exact: true })).toBeVisible();
  await expect(page.locator('main input[type=checkbox]')).toHaveCount(0);
  expect(requests.some(path => path.includes('/preseason/clans/'))).toBe(false);
});
test('clanless users never request another clan context', async ({ page }) => {
  const { requests } = await setup(page, { clanless: true });
  await expect(page.locator('main')).toContainText('Вступите в клан');
  expect(requests.some(path => path.includes('/preseason/clans/'))).toBe(false);
});
for (const width of [390, 1440]) test(`separate immutable land and relic claims at ${width}px`, async ({ page }) => {
  await page.setViewportSize({ width, height: 1000 });
  const { commands, requests } = await setup(page);
  const main = page.locator('main.preseason-page');
  await expect(main).toContainText('Будущая стартовая казна');
  await expect(main).toContainText('Резерв');
  await expect(main.locator('.preseason-relic')).toHaveCount(15);
  await expect(main.locator('.preseason-relic').first()).toContainText('+15%');
  for (const name of ['Reserved', 'Port', 'Fortress']) await expect(page.getByRole('checkbox', { name, exact: true })).toHaveCount(0);
  for (const name of ['Home', 'North', 'East']) await page.getByRole('checkbox', { name, exact: true }).check();
  await page.getByRole('button', { name: 'Проверить земли', exact: true }).click();
  const dialog = page.getByRole('alertdialog');
  await expect(dialog).toContainText('Island');
  await expect(dialog).toContainText('нельзя изменить');
  expect(commands).toHaveLength(1);
  await dialog.getByRole('button', { name: 'Подтвердить', exact: true }).click();
  await expect(dialog).toHaveCount(0);
  await expect(page.getByRole('button', { name: 'Проверить земли', exact: true })).toHaveCount(0);
  await page.getByRole('checkbox', { name: 'Реликвия 1', exact: true }).check();
  await page.getByRole('checkbox', { name: 'Реликвия 2', exact: true }).check();
  await page.getByRole('button', { name: 'Подтвердить реликвии', exact: true }).click();
  await expect(dialog).toContainText('Реликвия 1');
  await dialog.getByRole('button', { name: 'Подтвердить', exact: true }).click();
  await expect(page.getByRole('button', { name: 'Подтвердить реликвии', exact: true })).toHaveCount(0);
  expect(commands.map(c => c.body)).toEqual([{ selected: [10, 11, 12] }, { selected: [10, 11, 12], expected_revision: 4 }, { selected: ['royal_charter', 'war_foundry'], expected_revision: 5 }]);
  expect(requests.filter(p => p === '/api/v1/campaign/preseason/clans/7')).toHaveLength(1);
  await expect(main).not.toContainText(/72|24:|Купить|Запустить сезон/);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  expect(await main.locator('img').evaluateAll(images => images.every(img => img.complete && img.naturalWidth > 0))).toBe(true);
  await expect(dialog).toHaveCount(0);
  await page.evaluate(() => window.scrollTo(0, 0));
  await page.screenshot({ path: `test-results/preseason-${width}.png`, fullPage: true });
});
test('disconnected triple cannot reach server preview', async ({ page }) => {
  const { commands } = await setup(page);
  for (const name of ['Home', 'North', 'Island']) await page.getByRole('checkbox', { name, exact: true }).check();
  await expect(page.getByRole('button', { name: 'Проверить земли', exact: true })).toBeDisabled();
  expect(commands).toEqual([]);
});

test('one-way legacy adjacency connects the triple in either selection order', async ({ page }) => {
  const { commands } = await setup(page, { context: { territories: [
    { id: 10, name: 'Home', owner_clan_id: null, selection_owner_clan_id: 7, neighbours: [] },
    { id: 11, name: 'North', owner_clan_id: null, selection_owner_clan_id: null, neighbours: [10] },
    { id: 12, name: 'East', owner_clan_id: null, selection_owner_clan_id: null, neighbours: [11] },
  ] } });
  for (const name of ['Home', 'North', 'East']) await page.getByRole('checkbox', { name, exact: true }).check();
  await expect(page.getByRole('button', { name: 'Проверить земли', exact: true })).toBeEnabled();
  await page.getByRole('button', { name: 'Проверить земли', exact: true }).click();
  await expect(page.getByRole('alertdialog')).toContainText('Home');
  expect(commands.map(command => command.body)).toEqual([{ selected: [10, 11, 12] }]);
  await page.getByRole('alertdialog').getByRole('button', { name: 'Отмена', exact: true }).click();
  for (const name of ['Home', 'North', 'East']) await page.getByRole('checkbox', { name, exact: true }).uncheck();
  for (const name of ['East', 'North', 'Home']) await page.getByRole('checkbox', { name, exact: true }).check();
  await expect(page.getByRole('button', { name: 'Проверить земли', exact: true })).toBeEnabled();
});
test('members see the catalog and saved choices without write controls', async ({ page }) => {
  await setup(page, { context: { is_head: false, can_choose_lands: false, can_choose_relics: false } });
  await expect(page.locator('.preseason-relic')).toHaveCount(15);
  await expect(page.locator('main input[type=checkbox]')).toHaveCount(0);
  await expect(page.getByRole('button', { name: 'Проверить земли', exact: true })).toHaveCount(0);
  await expect(page.locator('main')).not.toContainText('Право выбора земель пока недоступно');
});
test('conflict refreshes rights and closes obsolete confirmation', async ({ page }) => {
  const { commands } = await setup(page, { conflict: true });
  for (const name of ['Home', 'North', 'East']) await page.getByRole('checkbox', { name, exact: true }).check();
  await page.getByRole('button', { name: 'Проверить земли', exact: true }).click();
  await expect(page.locator('main [role=alert]')).toBeVisible();
  await expect(page.getByRole('alertdialog')).toHaveCount(0);
  await expect(page.getByRole('button', { name: 'Проверить земли', exact: true })).toHaveCount(0);
  expect(commands).toHaveLength(1);
});

test('pending immutable claim cannot be submitted twice', async ({ page }) => {
  let release;
  const gate = new Promise(resolve => { release = resolve; });
  const { commands } = await setup(page, { gate });
  await page.getByRole('checkbox', { name: 'Реликвия 1', exact: true }).check();
  await page.getByRole('checkbox', { name: 'Реликвия 2', exact: true }).check();
  await page.getByRole('button', { name: 'Подтвердить реликвии', exact: true }).click();
  const confirm = page.getByRole('alertdialog').getByRole('button', { name: 'Подтвердить', exact: true });
  await confirm.evaluate(button => { button.click(); button.click(); });
  await expect.poll(() => commands.length).toBe(1);
  await expect(confirm).toBeDisabled();
  await expect(page.getByRole('alertdialog').getByRole('button', { name: 'Отмена' })).toBeDisabled();
  release();
  await expect(page.getByRole('alertdialog')).toHaveCount(0);
  expect(commands[0].body).toEqual({ selected: ['royal_charter', 'war_foundry'], expected_revision: 4 });
});

test('context closing between status and clan read removes all write controls', async ({ page }) => {
  await setup(page, { context: { open: false } });
  await expect(page.getByText('Предсезонный выбор закрыт.', { exact: true })).toBeVisible();
  await expect(page.locator('main input')).toHaveCount(0);
});

for (const [language, title] of [['en', 'Preseason selection'], ['de', 'Vorsaisonauswahl']]) test(`preseason copy supports ${language}`, async ({ page }) => {
  await setup(page, { language });
  await expect(page.getByRole('heading', { name: title, exact: true })).toBeVisible();
});

test('map notice links to open preseason independently of map preparation', async ({ page }) => {
  await setup(page);
  await page.route('**/api/v1/campaign/cycles/current', route => route.fulfill({ json: { mechanics_version: 'legacy', cycle: null, territory_battles: [], interseason: true, archived_season_id: 1 } }));
  for (const path of ['territories/', 'clans/', 'wars/active/']) await page.route(`**/api/v1/${path}`, route => route.fulfill({ json: [] }));
  await page.goto('/map');
  await expect(page.locator('.map-interseason-notice').getByRole('link', { name: 'Предсезонный выбор', exact: true })).toHaveAttribute('href', '/preseason');
});

test('own-clan overview links to preseason and hides old treasury', async ({ page }) => {
  await setup(page);
  await page.route('**/api/v1/campaign/cycles/current', route => route.fulfill({ json: { mechanics_version: 'legacy', cycle: null, territory_battles: [], interseason: true, archived_season_id: 1 } }));
  await page.route('**/api/v1/clans/7', route => route.fulfill({ json: { id: 7, name: 'Akatsuki', leader_id: 1, created_at: '2026-01-01', gold: 9876, members_count: 1 } }));
  await page.route('**/api/v1/clans/7/members', route => route.fulfill({ json: [{ user_id: 1, username: 'Head', rank: 'Глава' }] }));
  for (const path of ['territories/', 'clans/7/applications', 'clans/7/wars']) await page.route(`**/api/v1/${path}`, route => route.fulfill({ json: [] }));
  await page.goto('/clans/7');
  await expect(page.locator('.clan-prototype-overview').getByRole('link', { name: 'Предсезонный выбор', exact: true })).toHaveAttribute('href', '/preseason');
  await expect(page.locator('.clan-header-resource-ribbon')).toHaveCount(0);
  await expect(page.locator('.clan-prototype-overview')).toContainText('Будущая стартовая казна');
});

test('manual-start picker respects virtual reservations on the neutral live map', async ({ page }) => {
  await setup(page);
  await page.route('**/api/v1/campaign/cycles/2/clans/7/preparation', route => route.fulfill({ json: {
    cycle_id: 2, clan_id: 7, clan_name: 'Akatsuki',
    scout: { can_request: false },
    startup: { ready: true, can_claim: true, revision: 1, selected_lands: [] },
    territories: [
      { id: 10, name: 'Own reserve', owner_clan_id: null, selection_owner_clan_id: 7 },
      { id: 11, name: 'Other reserve', owner_clan_id: null, selection_owner_clan_id: 8 },
      { id: 12, name: 'Released reserve', owner_clan_id: 8, selection_owner_clan_id: null },
      { id: 13, name: 'Legacy enemy', owner_clan_id: 8 },
    ],
  } }));
  await page.goto('/campaign/cycles/2/preparation');
  await expect(page.getByRole('checkbox', { name: 'Own reserve', exact: true })).toBeVisible();
  await expect(page.getByRole('checkbox', { name: 'Other reserve', exact: true })).toHaveCount(0);
  await expect(page.getByRole('checkbox', { name: 'Released reserve', exact: true })).toBeVisible();
  await expect(page.getByRole('checkbox', { name: 'Legacy enemy', exact: true })).toHaveCount(0);
});

test('retention refusal displays server detail as text without HTML or a confirmation', async ({ page }) => {
  await setup(page);
  const detail = 'Нужно сохранить прежние пригодные земли. <img src=x onerror=alert(1)>';
  await page.route('**/preseason/clans/7/lands/preview', route => route.fulfill({ status: 409, json: { detail } }));
  for (const name of ['Home', 'North', 'East']) await page.getByRole('checkbox', { name, exact: true }).check();
  await page.getByRole('button', { name: 'Проверить земли', exact: true }).click();
  const alert = page.locator('main [role=alert]');
  await expect(alert).toHaveText(detail);
  await expect(alert.locator('img')).toHaveCount(0);
  await expect(page.getByRole('alertdialog')).toHaveCount(0);
});

for (const failure of ['network', 'nonstring', 'html']) test(`preseason ${failure} failure uses localized fallback`, async ({ page }) => {
  await setup(page, { language: 'de' });
  await page.route('**/preseason/clans/7/lands/preview', route => failure === 'network' ? route.abort('failed')
    : failure === 'html' ? route.fulfill({ status: 502, contentType: 'text/html', body: '<html>Internal gateway data</html>' })
      : route.fulfill({ status: 422, json: { detail: { diagnostic: 'Internal validation data' } } }));
  for (const name of ['Home', 'North', 'East']) await page.getByRole('checkbox', { name, exact: true }).check();
  await page.getByRole('button', { name: 'Gebiete prüfen', exact: true }).click();
  const alert = page.locator('main [role=alert]');
  await expect(alert).toContainText('Das Ergebnis konnte nicht bestätigt werden.');
  await expect(alert).not.toContainText(/Internal|Preseason request failed|TypeError|Conflict/);
});

for (const [language, expected] of [
  ['ru', ['выберите 3 из них', 'земель 1 или 2', '3 нейтральные земли взамен']],
  ['en', ['choose 3 of them', '1 or 2 suitable territories', '3 neutral territories instead']],
  ['de', ['wähle 3 davon', '1 oder 2 geeigneten Gebieten', 'stattdessen 3 neutrale Gebiete']],
]) test(`retention rules are explicit in ${language} without client-side retention validation`, async ({ page }) => {
  await setup(page, { language });
  const lands = page.locator('main section').filter({ has: page.locator('.preseason-lands') });
  for (const text of expected) await expect(lands).toContainText(text);
});

test('context load refusal also exposes a safe server string detail', async ({ page }) => {
  await setup(page);
  await page.route('**/preseason/clans/7', route => route.fulfill({ status: 403, json: { detail: 'Выбор доступен только участникам своего клана.' } }));
  await page.reload();
  await expect(page.locator('main [role=alert]')).toHaveText('Выбор доступен только участникам своего клана.');
});

test('territory cards do not expose technical region codes as user-facing text', async ({ page }) => {
  await setup(page, { context: { territories: [
    { id: 10, name: 'Home', region: 'eriador', owner_clan_id: null, selection_owner_clan_id: 7, neighbours: [11] },
    { id: 11, name: 'North', region: 'rhun', owner_clan_id: null, selection_owner_clan_id: null, neighbours: [10, 12] },
    { id: 12, name: 'East', region: 'misty-mountains', owner_clan_id: null, selection_owner_clan_id: null, neighbours: [11] },
  ] } });
  await expect(page.locator('.preseason-land')).toHaveCount(3);
  await expect(page.locator('.preseason-lands')).not.toContainText(/eriador|rhun|misty-mountains/);
  await expect(page.getByRole('checkbox', { name: 'Home', exact: true })).toBeVisible();
});

for (const [language, label, shire] of [['ru', 'Соседи:', 'Шир'], ['en', 'Neighbours:', 'Shire'], ['de', 'Nachbarn:', 'Auenland']]) test(`neighbour names include incoming edges without raw IDs in ${language}`, async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await setup(page, { language, context: { territories: [
    { id: 10, name: 'Home', owner_clan_id: null, selection_owner_clan_id: 7, neighbours: [999] },
    { id: 11, name: 'North', owner_clan_id: null, selection_owner_clan_id: null, neighbours: [10] },
    { id: 12, name: 'East', owner_clan_id: null, selection_owner_clan_id: null, neighbours: [11] },
    { id: 13, name: 'Reserved', owner_clan_id: null, selection_owner_clan_id: 8, neighbours: [10] },
    { id: 14, name: 'Шир', owner_clan_id: null, selection_owner_clan_id: 8, neighbours: [10] },
  ] } });
  const card = name => page.locator('.preseason-land').filter({ has: page.getByRole('checkbox', { name, exact: true }) });
  await expect(card('Home')).toContainText(`${label} North, Reserved, ${shire}`);
  await expect(card('North')).toContainText(`${label} Home, East`);
  await expect(card('East')).toContainText(`${label} North`);
  await expect(page.locator('.preseason-lands')).not.toContainText('999');
  await expect(page.getByRole('checkbox', { name: 'Reserved', exact: true })).toHaveCount(0);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await page.locator('.preseason-lands').screenshot({ path: `test-results/preseason-neighbours-${language}.png` });
});
