import { expect, test } from '@playwright/test';
import { readFileSync, mkdirSync } from 'node:fs';

test.use({ locale: 'ru-RU' });

const catalog = JSON.parse(readFileSync(new URL('../public/encyclopedia/ennorath/catalog.json', import.meta.url)));
const output = new URL('../../outputs/encyclopedia-vds-20260909/', import.meta.url);
mkdirSync(output, { recursive: true });

test.beforeEach(async ({ page }) => {
  await page.route('**/api/**', (route) => route.fulfill({ status: 401, contentType: 'application/json', body: '{"detail":"Not authenticated"}' }));
});

const ready = async (page) => {
  await expect(page.getByTestId('model-stage')).toHaveAttribute('data-status', 'ready', { timeout: 30000 });
  await expect.poll(() => page.locator('.encyclopedia-canvas').getAttribute('data-draw-calls')).not.toBe('0');
};

test('anonymous encyclopedia renders real geometry, levels and mounted animations', async ({ page }) => {
  await page.goto('/encyclopedia');
  await expect(page.getByRole('heading', { name: 'Арагорн', exact: true })).toBeVisible();
  await ready(page);
  await expect(page.getByTestId('entity-health')).toHaveText(/3\s*500/);
  const level = page.getByRole('slider', { name: /Уровень/ });
  await level.focus();
  await page.keyboard.press('End');
  await expect(page.getByTestId('entity-health')).toHaveText(/7\s*300/);
  await page.getByLabel('Облик', { exact: true }).selectOption('mounted');
  await ready(page);
  await page.getByLabel('Анимация', { exact: true }).selectOption('run');
  await expect.poll(async () => Number(await page.locator('.encyclopedia-canvas').getAttribute('data-animation-time'))).toBeGreaterThan(0.2);
  await page.getByRole('button', { name: 'Пауза', exact: true }).click();
  const frozen = await page.locator('.encyclopedia-canvas').getAttribute('data-animation-time');
  await page.getByRole('button', { name: 'Сбросить вид' }).click();
  await expect(page.locator('.encyclopedia-canvas')).toHaveAttribute('data-animation-time', frozen);
  await page.screenshot({ path: new URL('encyclopedia-desktop.png', output).pathname.replace(/^\/(\w:)/, '$1'), fullPage: true });
});

test('search, empty state, weapon mode and back navigation work', async ({ page }) => {
  await page.goto('/encyclopedia');
  const search = page.getByRole('searchbox');
  await search.fill('no such entity');
  await expect(page.getByText('Ничего не найдено. Измените поиск или фильтры.')).toBeVisible();
  await search.fill('Фарамир');
  await expect(page.getByRole('heading', { name: 'Фарамир', exact: true })).toBeVisible();
  await ready(page);
  await page.getByLabel('Оружие', { exact: true }).selectOption('bow');
  await ready(page);
  await page.getByLabel('Анимация', { exact: true }).selectOption('attack');
  await page.getByRole('slider', { name: /Уровень/ }).focus();
  await page.keyboard.press('End');
  await expect(page.getByLabel('Облик', { exact: true })).toHaveValue('armored');
  await ready(page);
  await search.fill('');
  await page.getByRole('button', { name: 'Боромир Герой', exact: true }).click();
  await expect(page).toHaveURL(/entity=boromir/);
  await page.reload();
  await expect(page.getByRole('heading', { name: 'Боромир', exact: true })).toBeVisible();
  await ready(page);
});

for (const profile of catalog.profiles) {
  test(`actual game model loads for ${profile.id}`, async ({ page }) => {
    test.setTimeout(60000);
    const errors = [];
    page.on('pageerror', (error) => errors.push(error.message));
    await page.goto(`/encyclopedia?entity=${profile.id}`);
    await expect(page.getByRole('heading', { name: profile.name, exact: true })).toBeVisible();
    await ready(page);
    expect(Number(await page.locator('.encyclopedia-canvas').getAttribute('data-draw-calls')), profile.id).toBeGreaterThan(0);
    expect(errors).toEqual([]);
  });
}

test('failed model and failed catalogue offer a working retry', async ({ page }) => {
  await page.route('**/encyclopedia/ennorath/catalog.json', (route) => route.fulfill({ status: 503, body: '' }));
  await page.goto('/encyclopedia');
  await expect(page.getByRole('alert')).toContainText('Не удалось загрузить энциклопедию');
  await page.unroute('**/encyclopedia/ennorath/catalog.json');
  await page.route('**/*.glb', (route) => route.fulfill({ status: 404, body: '' }));
  await page.getByRole('button', { name: 'Повторить', exact: true }).click();
  await expect(page.getByTestId('model-stage')).toHaveAttribute('data-status', 'error');
  await page.unroute('**/*.glb');
  await page.getByRole('button', { name: 'Повторить', exact: true }).click();
  await ready(page);
});

for (const [language, title, message] of [
  ['ru', 'Энциклопедия', 'Модели 2.02 пока не добавлены.'],
  ['en', 'Encyclopedia', 'Models for 2.02 have not been added yet.'],
  ['de', 'Enzyklopädie', 'Modelle für 2.02 wurden noch nicht hinzugefügt.'],
]) {
  test(`encyclopedia editions are localized and 2.02 remains disabled in ${language}`, async ({ page }) => {
    await page.addInitScript((value) => localStorage.setItem('language', value), language);
    await page.goto('/encyclopedia');
    await expect(page.getByRole('heading', { name: title, exact: true })).toBeVisible();
    await expect(page.getByRole('tab', { name: 'Ennorath', exact: true })).toHaveAttribute('aria-selected', 'true');
    const unavailable = page.getByRole('tab', { name: '2.02', exact: true });
    await expect(unavailable).toBeDisabled();
    await expect(unavailable).toHaveAttribute('aria-selected', 'false');
    await expect(page.getByText(message, { exact: true })).toBeVisible();
    await expect(page.locator('a[href^="/guides"]')).toHaveCount(0);
    await ready(page);
    await page.reload();
    await expect(unavailable).toBeDisabled();
    await ready(page);
    await page.screenshot({ path: new URL(`encyclopedia-${language}.png`, output).pathname.replace(/^\/(\w:)/, '$1'), fullPage: true });
  });
}

test('mobile menu and unit formation fit narrow screens', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto('/encyclopedia');
  await page.getByRole('button', { name: 'Открыть меню', exact: true }).click();
  await page.getByRole('menuitem', { name: 'Энциклопедия', exact: true }).click();
  await page.getByLabel('Фракция', { exact: true }).selectOption('gondor');
  await page.getByLabel('Тип', { exact: true }).selectOption('unit');
  await ready(page);
  await page.getByLabel('Показать отряд').check();
  await ready(page);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
  await page.screenshot({ path: new URL('encyclopedia-mobile.png', output).pathname.replace(/^\/(\w:)/, '$1'), fullPage: true });
  await expect(page.getByRole('tab', { name: '2.02', exact: true })).toBeDisabled();
  await expect(page.locator('a[href^="/guides"]')).toHaveCount(0);
});
