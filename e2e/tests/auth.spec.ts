import { test, expect } from '@playwright/test';

/**
 * Authentication Flow E2E Tests
 * 
 * Tests OAuth login, logout, and session management
 */

test.describe('Authentication Flow', () => {
  test.beforeEach(async ({ page }) => {
    // Navigate to the home page
    await page.goto('/');
  });

  test('should display login page for unauthenticated users', async ({ page }) => {
    await expect(page).toHaveURL('/');
    await expect(page.locator('text=Login')).toBeVisible();
  });

  test('should redirect to dashboard after successful Google OAuth login', async ({ page, context }) => {
    // Mock the OAuth callback by setting a session cookie
    // In real scenario, this would be done through OAuth flow
    await context.addCookies([
      {
        name: 'tc_session',
        value: 'mock-session-token-for-e2e-testing',
        domain: 'localhost',
        path: '/',
        httpOnly: true,
        secure: false,
        sameSite: 'Lax',
      },
    ]);

    // Mock the /api/auth/me endpoint to return a user
    await page.route('**/api/auth/me', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          id: '00000000-0000-0000-0000-000000000001',
          email: 'free-user@example.com',
          name: 'Free User',
          plan: 'free',
        }),
      });
    });

    // Navigate to the app
    await page.goto('/');

    // Should redirect to search page (main authenticated page)
    await expect(page).toHaveURL(/\/search/);
    
    // Check if user name is visible in header/nav
    await expect(page.locator('text=Free User')).toBeVisible();
  });

  test('should handle OAuth callback errors gracefully', async ({ page }) => {
    // Navigate to OAuth callback with error parameter
    await page.goto('/auth/callback?error=access_denied');

    // Should show error message
    await expect(page.locator('text=Authentication failed')).toBeVisible();
    
    // Should have option to try again
    await expect(page.locator('text=Try again')).toBeVisible();
  });

  test('should logout and clear session', async ({ page, context }) => {
    // Setup authenticated session
    await context.addCookies([
      {
        name: 'tc_session',
        value: 'mock-session-token',
        domain: 'localhost',
        path: '/',
        httpOnly: true,
        secure: false,
        sameSite: 'Lax',
      },
    ]);

    // Mock the /api/auth/me endpoint
    await page.route('**/api/auth/me', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          id: '00000000-0000-0000-0000-000000000001',
          email: 'free-user@example.com',
          name: 'Free User',
          plan: 'free',
        }),
      });
    });

    // Mock logout endpoint
    await page.route('**/api/auth/logout', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ success: true }),
      });
    });

    // Navigate to authenticated page
    await page.goto('/search');
    await expect(page.locator('text=Free User')).toBeVisible();

    // Click logout button
    const logoutButton = page.locator('button:has-text("Logout"), a:has-text("Logout")');
    await logoutButton.click();

    // Should redirect to home/login
    await expect(page).toHaveURL('/');
    
    // Should show login option
    await expect(page.locator('text=Login')).toBeVisible();
  });

  test('should persist session across page reloads', async ({ page, context }) => {
    // Setup authenticated session
    await context.addCookies([
      {
        name: 'tc_session',
        value: 'mock-session-token',
        domain: 'localhost',
        path: '/',
        httpOnly: true,
        secure: false,
        sameSite: 'Lax',
      },
    ]);

    // Mock the /api/auth/me endpoint
    await page.route('**/api/auth/me', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          id: '00000000-0000-0000-0000-000000000001',
          email: 'free-user@example.com',
          name: 'Free User',
          plan: 'free',
        }),
      });
    });

    // Navigate to authenticated page
    await page.goto('/search');
    await expect(page.locator('text=Free User')).toBeVisible();

    // Reload the page
    await page.reload();

    // Should still be authenticated
    await expect(page.locator('text=Free User')).toBeVisible();
  });

  test('should redirect unauthenticated users to login from protected routes', async ({ page }) => {
    // Mock the /api/auth/me endpoint to return 401
    await page.route('**/api/auth/me', async (route) => {
      await route.fulfill({
        status: 401,
        contentType: 'application/json',
        body: JSON.stringify({ error: 'Unauthorized' }),
      });
    });

    // Try to access protected route
    await page.goto('/search');

    // Should redirect to login
    await expect(page).toHaveURL('/');
    await expect(page.locator('text=Login')).toBeVisible();
  });
});

test.describe('Authentication Flow - Mobile', () => {
  test.use({ viewport: { width: 375, height: 667 } }); // iPhone SE size

  test('should handle login on mobile viewport', async ({ page, context }) => {
    // Mock authenticated session
    await context.addCookies([
      {
        name: 'tc_session',
        value: 'mock-session-token',
        domain: 'localhost',
        path: '/',
        httpOnly: true,
        secure: false,
        sameSite: 'Lax',
      },
    ]);

    // Mock the /api/auth/me endpoint
    await page.route('**/api/auth/me', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          id: '00000000-0000-0000-0000-000000000001',
          email: 'free-user@example.com',
          name: 'Free User',
          plan: 'free',
        }),
      });
    });

    await page.goto('/search');

    // Check mobile navigation works
    await expect(page.locator('text=Free User')).toBeVisible();
  });
});
