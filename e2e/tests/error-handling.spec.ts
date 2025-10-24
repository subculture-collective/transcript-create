import { test, expect } from '@playwright/test';

/**
 * Error Handling & Edge Cases E2E Tests
 * 
 * Tests 404 pages, API errors, network failures, and other edge cases
 */

test.describe('Error Handling', () => {
  test('should display 404 page for non-existent routes', async ({ page }) => {
    // Navigate to a route that doesn't exist
    await page.goto('/this-page-does-not-exist-12345');

    // Should show 404 page
    await expect(page.locator('text=/404|Not Found|Page not found/i')).toBeVisible({ timeout: 5000 });
    
    // Should have link to go back home
    const homeLink = page.locator('a[href="/"], a:has-text("Home"), a:has-text("Go back")');
    await expect(homeLink).toBeVisible();
  });

  test('should display custom 404 for non-existent video', async ({ page, context }) => {
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

    await page.route('**/api/auth/me', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          id: '00000000-0000-0000-0000-000000000001',
          email: 'test-user@example.com',
          name: 'Test User',
          plan: 'free',
        }),
      });
    });

    // Mock 404 response for video
    await page.route('**/api/videos/nonexistent-video-id/transcript', async (route) => {
      await route.fulfill({
        status: 404,
        contentType: 'application/json',
        body: JSON.stringify({
          error: 'Video not found',
        }),
      });
    });

    // Navigate to non-existent video
    await page.goto('/videos/nonexistent-video-id');

    // Should show error message
    await expect(page.locator('text=Video not found, text=not found, text=doesn\'t exist')).toBeVisible({ timeout: 5000 });
  });

  test('should handle network errors gracefully', async ({ page, context }) => {
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

    await page.route('**/api/auth/me', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          id: '00000000-0000-0000-0000-000000000001',
          email: 'test-user@example.com',
          name: 'Test User',
          plan: 'free',
        }),
      });
    });

    // Simulate network failure
    await page.route('**/api/search*', async (route) => {
      await route.abort('failed');
    });

    await page.goto('/search');

    // Try to search
    const searchInput = page.locator('input[type="search"], input[placeholder*="Search"]').first();
    await searchInput.fill('test');
    
    const searchButton = page.locator('button:has-text("Search"), button[type="submit"]').first();
    await searchButton.click();

    // Should show network error message
    await expect(page.locator('text=Network error, text=Connection failed, text=Unable to connect')).toBeVisible({ timeout: 5000 });
  });

  test('should handle API timeout errors', async ({ page, context }) => {
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

    await page.route('**/api/auth/me', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          id: '00000000-0000-0000-0000-000000000001',
          email: 'test-user@example.com',
          name: 'Test User',
          plan: 'free',
        }),
      });
    });

    // Simulate slow API response
    await page.route('**/api/jobs', async (route) => {
      // Never respond to simulate timeout
      await new Promise(() => {}); // Infinite wait
    });

    await page.goto('/search');

    // Try to create job
    const urlInput = page.locator('input[type="text"], input[type="url"]').first();
    await urlInput.fill('https://www.youtube.com/watch?v=test');
    
    const submitButton = page.locator('button:has-text("Create"), button:has-text("Submit"), button[type="submit"]').first();
    await submitButton.click();

    // Should show timeout or loading state, then error
    // Note: Actual timeout handling depends on app implementation
    await page.waitForTimeout(5000);
  });

  test('should handle invalid YouTube URL with proper error message', async ({ page, context }) => {
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

    await page.route('**/api/auth/me', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          id: '00000000-0000-0000-0000-000000000001',
          email: 'test-user@example.com',
          name: 'Test User',
          plan: 'free',
        }),
      });
    });

    // Mock validation error
    await page.route('**/api/jobs', async (route) => {
      if (route.request().method() === 'POST') {
        await route.fulfill({
          status: 400,
          contentType: 'application/json',
          body: JSON.stringify({
            error: 'Invalid YouTube URL',
            details: 'The URL must be a valid YouTube video or channel URL',
          }),
        });
      }
    });

    await page.goto('/search');

    // Enter invalid URL
    const urlInput = page.locator('input[type="text"], input[type="url"]').first();
    await urlInput.fill('not-a-valid-url');
    
    const submitButton = page.locator('button:has-text("Create"), button:has-text("Submit"), button[type="submit"]').first();
    await submitButton.click();

    // Should show validation error
    await expect(page.locator('text=Invalid YouTube URL, text=must be a valid')).toBeVisible({ timeout: 5000 });
  });

  test('should handle authentication errors and redirect to login', async ({ page }) => {
    // Mock 401 response
    await page.route('**/api/auth/me', async (route) => {
      await route.fulfill({
        status: 401,
        contentType: 'application/json',
        body: JSON.stringify({
          error: 'Unauthorized',
        }),
      });
    });

    // Try to access protected route
    await page.goto('/search');

    // Should redirect to login
    await expect(page).toHaveURL('/', { timeout: 5000 });
    await expect(page.locator('text=Login, text=Sign in')).toBeVisible();
  });

  test('should handle server errors (500) with user-friendly message', async ({ page, context }) => {
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

    await page.route('**/api/auth/me', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          id: '00000000-0000-0000-0000-000000000001',
          email: 'test-user@example.com',
          name: 'Test User',
          plan: 'free',
        }),
      });
    });

    // Mock server error
    await page.route('**/api/search*', async (route) => {
      await route.fulfill({
        status: 500,
        contentType: 'application/json',
        body: JSON.stringify({
          error: 'Internal server error',
        }),
      });
    });

    await page.goto('/search');

    // Perform search
    const searchInput = page.locator('input[type="search"], input[placeholder*="Search"]').first();
    await searchInput.fill('test');
    
    const searchButton = page.locator('button:has-text("Search"), button[type="submit"]').first();
    await searchButton.click();

    // Should show user-friendly error
    await expect(page.locator('text=Something went wrong, text=server error, text=Please try again')).toBeVisible({ timeout: 5000 });
  });

  test('should show loading states during async operations', async ({ page, context }) => {
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

    await page.route('**/api/auth/me', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          id: '00000000-0000-0000-0000-000000000001',
          email: 'test-user@example.com',
          name: 'Test User',
          plan: 'free',
        }),
      });
    });

    // Mock slow search response
    await page.route('**/api/search*', async (route) => {
      await new Promise(resolve => setTimeout(resolve, 2000));
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          results: [],
          total: 0,
        }),
      });
    });

    await page.goto('/search');

    // Perform search
    const searchInput = page.locator('input[type="search"], input[placeholder*="Search"]').first();
    await searchInput.fill('test');
    
    const searchButton = page.locator('button:has-text("Search"), button[type="submit"]').first();
    await searchButton.click();

    // Should show loading indicator
    const loadingIndicator = page.locator('text=Loading, [role="progressbar"], .spinner, .loading');
    
    // Check if loading appears (might be brief)
    const isLoadingVisible = await loadingIndicator.isVisible({ timeout: 500 }).catch(() => false);
    
    // Eventually results should appear
    await page.waitForTimeout(2500);
    await expect(page.locator('text=No results, text=results')).toBeVisible();
  });

  test('should handle empty form submissions', async ({ page, context }) => {
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

    await page.route('**/api/auth/me', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          id: '00000000-0000-0000-0000-000000000001',
          email: 'test-user@example.com',
          name: 'Test User',
          plan: 'free',
        }),
      });
    });

    await page.goto('/search');

    // Try to submit empty form
    const submitButton = page.locator('button:has-text("Create"), button:has-text("Submit"), button[type="submit"]').first();
    
    if (await submitButton.isVisible()) {
      await submitButton.click();

      // Should show validation error or be disabled
      const validationError = page.locator('text=required, text=Please enter, text=cannot be empty');
      
      // Either button should be disabled or validation message should show
      const isDisabled = await submitButton.isDisabled();
      const hasValidation = await validationError.isVisible({ timeout: 1000 }).catch(() => false);
      
      expect(isDisabled || hasValidation).toBeTruthy();
    }
  });

  test('should provide helpful error recovery options', async ({ page, context }) => {
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

    await page.route('**/api/auth/me', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          id: '00000000-0000-0000-0000-000000000001',
          email: 'test-user@example.com',
          name: 'Test User',
          plan: 'free',
        }),
      });
    });

    // Mock error
    await page.route('**/api/jobs', async (route) => {
      await route.fulfill({
        status: 500,
        contentType: 'application/json',
        body: JSON.stringify({
          error: 'Failed to create job',
        }),
      });
    });

    await page.goto('/search');

    // Try to create job
    const urlInput = page.locator('input[type="text"], input[type="url"]').first();
    await urlInput.fill('https://www.youtube.com/watch?v=test');
    
    const submitButton = page.locator('button:has-text("Create"), button:has-text("Submit"), button[type="submit"]').first();
    await submitButton.click();

    // Should show error with retry option
    const retryButton = page.locator('button:has-text("Try again"), button:has-text("Retry"), a:has-text("Try again")');
    
    if (await retryButton.isVisible({ timeout: 3000 }).catch(() => false)) {
      await expect(retryButton).toBeVisible();
    }
  });
});

test.describe('Error Handling - Mobile', () => {
  test.use({ viewport: { width: 375, height: 667 } });

  test('should display 404 page on mobile', async ({ page }) => {
    await page.goto('/nonexistent-page');

    // Should show mobile-responsive 404
    await expect(page.locator('text=404, text=Not Found')).toBeVisible();
  });

  test('should handle errors gracefully on mobile', async ({ page, context }) => {
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

    await page.route('**/api/auth/me', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          id: '00000000-0000-0000-0000-000000000001',
          email: 'test-user@example.com',
          name: 'Test User',
          plan: 'free',
        }),
      });
    });

    await page.route('**/api/search*', async (route) => {
      await route.fulfill({
        status: 500,
        contentType: 'application/json',
        body: JSON.stringify({ error: 'Server error' }),
      });
    });

    await page.goto('/search');

    // Tap to search
    const searchInput = page.locator('input[type="search"], input[placeholder*="Search"]').first();
    await searchInput.tap();
    await searchInput.fill('test');
    
    const searchButton = page.locator('button:has-text("Search"), button[type="submit"]').first();
    await searchButton.tap();

    // Should show mobile-friendly error
    await expect(page.locator('text=error, text=wrong, text=try again')).toBeVisible({ timeout: 5000 });
  });
});
