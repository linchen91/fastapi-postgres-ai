import { test, expect } from '@playwright/test';

test.describe('Login page', () => {
  test.beforeEach(async ({ page }) => {
    // Start each test on the login route with a clean localStorage.
    await page.goto('/');
  });

  test('renders the login form', async ({ page }) => {
    await expect(page.getByRole('heading', { name: 'Login' })).toBeVisible();
    await expect(page.getByLabel('Account')).toBeVisible();
    await expect(page.getByLabel('Password')).toBeVisible();
    await expect(page.getByRole('button', { name: 'Login' })).toBeVisible();
  });

  test('shows an error on failed login', async ({ page }) => {
    // Mock a 400 from the auth endpoint so the test stays offline.
    await page.route('**/auth/token', (route) =>
      route.fulfill({
        status: 400,
        contentType: 'application/json',
        body: JSON.stringify({ detail: 'Incorrect account or password' }),
      })
    );

    await page.getByLabel('Account').fill('wrong-user');
    await page.getByLabel('Password').fill('wrong-pass');
    await page.getByRole('button', { name: 'Login' }).click();

    await expect(page.getByText('Incorrect account or password')).toBeVisible();
    // Still on the login route.
    await expect(page).toHaveURL(/\/$/);
  });

  test('redirects to /home on successful login', async ({ page }) => {
    // Mock a successful token response.
    await page.route('**/auth/token', (route) =>
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ access_token: 'e2e-test-token', token_type: 'bearer' }),
      })
    );
    // Stub downstream API calls the Home page makes so it renders offline.
    await page.route('**/users/**', (route) =>
      route.fulfill({ status: 200, contentType: 'application/json', body: '[]' })
    );
    await page.route('**/roles/**', (route) =>
      route.fulfill({ status: 200, contentType: 'application/json', body: '[]' })
    );
    await page.route('**/devices/**', (route) =>
      route.fulfill({ status: 200, contentType: 'application/json', body: '[]' })
    );
    await page.route('**/events**', (route) =>
      route.fulfill({ status: 200, contentType: 'application/json', body: '[]' })
    );

    await page.getByLabel('Account').fill('admin');
    await page.getByLabel('Password').fill('secret');
    await page.getByRole('button', { name: 'Login' }).click();

    await expect(page).toHaveURL(/\/home$/);
    // Token persisted for subsequent authenticated requests.
    const token = await page.evaluate(() => localStorage.token);
    expect(token).toBe('e2e-test-token');
    const account = await page.evaluate(() => localStorage.account);
    expect(account).toBe('admin');
  });
});
