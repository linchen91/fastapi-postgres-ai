import { test, expect } from '@playwright/test';

const ADMIN_ACCOUNT = process.env.AZURE_ADMIN_ACCOUNT || 'admin';
const ADMIN_PASSWORD = process.env.AZURE_ADMIN_PASSWORD || 'admin123';

async function login(page, account, password) {
  await page.goto('/');
  await page.getByLabel('Account').fill(account);
  await page.getByLabel('Password').fill(password);
  await page.getByRole('button', { name: 'Login' }).click();
}

test.describe('Azure deployment (live, no mocks)', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/');
  });

  test('renders the login form', async ({ page }) => {
    await expect(page.getByRole('heading', { name: 'Login' })).toBeVisible();
    await expect(page.getByLabel('Account')).toBeVisible();
    await expect(page.getByLabel('Password')).toBeVisible();
    await expect(page.getByRole('button', { name: 'Login' })).toBeVisible();
  });

  test('rejects bad credentials against the real API', async ({ page }) => {
    await login(page, 'wrong-user', 'wrong-pass');

    await expect(page.getByText('Account or Password error')).toBeVisible();
    await expect(page).toHaveURL(/\/$/);
    expect(await page.evaluate(() => localStorage.token)).toBeUndefined();
  });

  test('admin login reaches the dashboard', async ({ page }) => {
    await login(page, ADMIN_ACCOUNT, ADMIN_PASSWORD);

    await expect(page).toHaveURL(/\/home$/);
    const token = await page.evaluate(() => localStorage.token);
    expect(token).toBeTruthy();
    expect(await page.evaluate(() => localStorage.account)).toBe(ADMIN_ACCOUNT);
  });

  test('serves Swagger UI at /docs instead of the SPA shell', async ({ page }) => {
    await page.goto('/docs');

    await expect(page.locator('.swagger-ui .info .title')).toBeVisible();
    expect(await page.locator('.opblock').count()).toBeGreaterThan(0);
    await expect(page.locator('#root')).toHaveCount(0);
  });

  test('news page loads traffic messages without a network error', async ({ page }) => {
    await login(page, ADMIN_ACCOUNT, ADMIN_PASSWORD);
    await expect(page).toHaveURL(/\/home$/);

    await page.goto('/news');

    await expect(page.getByRole('heading', { name: 'Traffic News' })).toBeVisible();
    await expect(page.locator('.alert-danger')).toHaveCount(0);
    await expect(page.getByRole('button', { name: 'Refresh' })).toBeEnabled();
  });

  test('dashboard renders authenticated API data', async ({ page }) => {
    await login(page, ADMIN_ACCOUNT, ADMIN_PASSWORD);

    await expect(page).toHaveURL(/\/home$/);
    await expect(page.locator('.alert-danger')).toHaveCount(0);
  });
});
