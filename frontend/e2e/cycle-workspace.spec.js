import { test, expect } from '@playwright/test';

const base = '/campaign/cycles/1';
const sections = [
  ['Битвы', ''], ['Отряды', '/orders'], ['Подкрепления', '/reinforcements'],
  ['Дипломатия', '/diplomacy'], ['Подготовка', '/preparation'],
];

async function mockApi(page) {
  await page.addInitScript(() => localStorage.setItem('language', 'ru'));
  await page.route('**/api/v1/**', route => {
    const path = new URL(route.request().url()).pathname;
    let payload = {};
    if (path.endsWith('/auth/session') || path.endsWith('/users/me')) payload = {
      id: 1, username: 'tester', language: 'ru', is_verified: true, is_claimed: true,
      role: { name: 'user' }, onboarding_completed: true,
    };
    else if (path.endsWith('/clans/my')) return route.fulfill({ status: 404, json: { detail: 'No clan' } });
    else if (path === `/api/v1${base}`) payload = { id: 1, number: 1, phase: 'battle' };
    else if (path === `/api/v1${base}/battles`) payload = { battles: [] };
    else if (path.includes('/diplomacy/cycles/1')) payload = { relations: Array.from({ length: 20 }, (_, i) => ({
      clan_low_id: i * 2 + 1, clan_high_id: i * 2 + 2,
      clan_low: { name: `First clan ${i}` }, clan_high: { name: `Second clan ${i}` },
      status: 'hostile', declarations: {},
    })) };
    else if (path.endsWith('/interception')) return route.fulfill({ status: 404, json: { detail: 'Unavailable' } });
    else if (path.includes('notifications')) payload = { items: [], unread_count: 0, total: 0 };
    else if (path.includes('presence')) payload = { items: [] };
    else if (path.includes('localization')) payload = [];
    return route.fulfill({ json: payload });
  });
}

async function expectNavigation(page, active) {
  const nav = page.locator('.cycle-navigation');
  await expect(nav).toHaveCount(1);
  await expect(nav).toBeVisible();
  for (const [name, path] of sections) {
    const link = nav.getByRole('link', { name, exact: true });
    await expect(link).toBeVisible();
    await expect(link).toHaveAttribute('href', `${base}${path}`);
  }
  await expect(nav.locator('[aria-current="page"]')).toHaveText(active);
  await expect(page.locator('main > a').filter({ hasText: /Битвы|Назад к битвам/ })).toBeHidden();
}

test.beforeEach(async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await mockApi(page);
});

for (const [active, path] of [...sections, ['Подкрепления', '/interception?dispatch_id=test']]) {
  test(`shared battle navigation on direct route ${path || '/'}`, async ({ page }) => {
    const errors = [];
    page.on('pageerror', error => errors.push(error.message));
    await page.goto(`${base}${path}`);
    await expectNavigation(page, active);
    await expect(page.locator('main')).toBeVisible();
    expect(errors).toEqual([]);
  });
}

test('navigation remains the same DOM node across child routes and history', async ({ page }) => {
  await page.goto(base);
  await expectNavigation(page, 'Битвы');
  const nav = await page.locator('.cycle-navigation').elementHandle();
  for (const [name, path] of sections.slice(1)) {
    await page.locator('.cycle-navigation').getByRole('link', { name, exact: true }).click();
    await expect(page).toHaveURL(`${base}${path}`);
    await expectNavigation(page, name);
    expect(await nav.evaluate(element => element === document.querySelector('.cycle-navigation'))).toBe(true);
  }
  await page.goBack();
  await expectNavigation(page, 'Дипломатия');
  await page.goForward();
  await expectNavigation(page, 'Подготовка');
});

test('lazy child loading never hides the shared navigation', async ({ page }) => {
  let release;
  const gate = new Promise(resolve => { release = resolve; });
  let requested;
  const started = new Promise(resolve => { requested = resolve; });
  await page.route('**/src/pages/CycleOrdersPage.jsx*', async route => {
    requested();
    await gate;
    await route.continue();
  });
  await page.goto(base);
  const nav = await page.locator('.cycle-navigation').elementHandle();
  await page.locator('.cycle-navigation').getByRole('link', { name: 'Отряды', exact: true }).click();
  try {
    await started;
    await expect(page.locator('.cycle-workspace__content [role="status"]')).toBeVisible();
    await expectNavigation(page, 'Отряды');
    expect(await nav.evaluate(element => element.isConnected && getComputedStyle(element).display !== 'none')).toBe(true);
  } finally {
    release();
  }
  await expect(page.locator('.cycle-orders')).toBeVisible();
});

for (const banner of [false, true]) {
  test(`navigation stays below the actual sticky header, preview banner ${banner}`, async ({ page }) => {
    await page.goto(`${base}/diplomacy`);
    await expectNavigation(page, 'Дипломатия');
    if (banner) await page.evaluate(() => {
      const banner = document.createElement('aside');
      banner.className = 'admin-preview-banner';
      banner.textContent = 'Admin preview';
      document.querySelector('.cw-navigation').before(banner);
    });
    await expect(page.locator('.cd-relation')).toHaveCount(20);
    await page.evaluate(() => window.scrollTo(0, 1000));
    await expect.poll(() => page.locator('.cycle-navigation').evaluate(element => {
      const rect = element.getBoundingClientRect();
      const header = document.querySelector('.cw-navigation').getBoundingClientRect();
      return Math.abs(rect.top - header.bottom) < 2 && rect.bottom < innerHeight;
    })).toBe(true);
    await expectNavigation(page, 'Дипломатия');
    for (const link of await page.locator('.cycle-navigation a').all()) await expect(link).toBeInViewport();
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    await page.screenshot({ path: `test-results/cycle-workspace-sticky-${banner}.png` });
  });
}

test('economy direct link stays outside the battle workspace', async ({ page }) => {
  await page.goto(`${base}/economy`);
  await expect(page.locator('.cycle-economy')).toBeVisible();
  await expect(page.locator('.cycle-navigation')).toHaveCount(0);
  await expect(page.locator('.cycle-workspace')).toHaveCount(0);
});

test('battle navigation offers the map but never treasury', async ({ page }) => {
  await page.goto(base);
  const nav = page.locator('.cycle-navigation');
  await expect(nav).toBeVisible();
  await expect(nav.locator('a[href$="/economy"]')).toHaveCount(0);
  await expect(nav.getByRole('link', { name: 'Открыть карту', exact: true })).toHaveAttribute('href', '/map');
});

for (const width of [390, 1024]) {
  test(`all workspace links stay visible and fit at ${width}px`, async ({ page }) => {
    await page.setViewportSize({ width, height: 900 });
    await page.goto(`${base}/diplomacy`);
    await expectNavigation(page, 'Дипломатия');
    await expect(page.locator('.cd-relation')).toHaveCount(20);
    await page.evaluate(() => window.scrollTo(0, 800));
    const nav = page.locator('.cycle-navigation');
    for (const link of await nav.getByRole('link').all()) await expect(link).toBeInViewport();
    expect(await nav.evaluate(element => {
      const header = document.querySelector('.cw-navigation').getBoundingClientRect();
      return element.getBoundingClientRect().top >= header.bottom - 1
        && [...element.querySelectorAll('a span')].every(span => {
          const text = span.getBoundingClientRect();
          const link = span.closest('a').getBoundingClientRect();
          return text.left >= link.left && text.right <= link.right && text.bottom <= link.bottom;
        });
    })).toBe(true);
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    await page.screenshot({ path: `test-results/cycle-workspace-${width}.png` });
  });
}
