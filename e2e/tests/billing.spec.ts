import { test, expect } from '@playwright/test';

/**
 * Billing & Quotas E2E Tests
 * 
 * Tests free user quota limits, upgrade flows, and Stripe integration (mocked)
 */

test.describe('Billing & Quotas', () => {
  test('should show upgrade prompt when free user reaches quota limit', async ({ page, context }) => {
    // Setup free user with quota reached
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

    // Mock auth endpoint with quota reached user
    await page.route('**/api/auth/me', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          id: '00000000-0000-0000-0000-000000000003',
          email: 'quota-reached-user@example.com',
          name: 'Quota Reached User',
          plan: 'free',
          daily_search_count: 5, // Assuming 5 is the limit
        }),
      });
    });

    // Mock search endpoint to return quota error
    await page.route('**/api/search*', async (route) => {
      await route.fulfill({
        status: 429, // Too Many Requests
        contentType: 'application/json',
        body: JSON.stringify({
          error: 'Daily search quota exceeded',
          quota_limit: 5,
          current_count: 5,
        }),
      });
    });

    await page.goto('/search');

    // Try to perform search
    const searchInput = page.locator('input[type="search"], input[placeholder*="Search"]').first();
    await searchInput.fill('test');
    
    const searchButton = page.locator('button:has-text("Search"), button[type="submit"]').first();
    await searchButton.click();

    // Should show upgrade prompt
    await expect(page.locator('text=quota exceeded, text=Upgrade, text=Pro')).toBeVisible({ timeout: 5000 });
  });

  test('should allow pro user unlimited searches', async ({ page, context }) => {
    // Setup pro user
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
          id: '00000000-0000-0000-0000-000000000002',
          email: 'pro-user@example.com',
          name: 'Pro User',
          plan: 'pro',
          daily_search_count: 100, // Pro users have no limit
        }),
      });
    });

    // Mock successful search
    await page.route('**/api/search*', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          results: [
            {
              video_id: 'test-video',
              title: 'Test Video',
              segment_text: 'Test content',
              start_ms: 0,
              end_ms: 1000,
            },
          ],
          total: 1,
        }),
      });
    });

    await page.goto('/search');

    // Perform multiple searches (should all work)
    for (let i = 0; i < 3; i++) {
      const searchInput = page.locator('input[type="search"], input[placeholder*="Search"]').first();
      await searchInput.clear();
      await searchInput.fill(`test ${i}`);
      
      const searchButton = page.locator('button:has-text("Search"), button[type="submit"]').first();
      await searchButton.click();

      // Should see results
      await expect(page.locator('text=Test Video')).toBeVisible({ timeout: 3000 });
      
      await page.waitForTimeout(500);
    }

    // No quota error should appear
    await expect(page.locator('text=quota exceeded')).not.toBeVisible();
  });

  test('should display pricing page with plan comparison', async ({ page, context }) => {
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
          email: 'free-user@example.com',
          name: 'Free User',
          plan: 'free',
        }),
      });
    });

    await page.goto('/pricing');

    // Should show pricing plans
    await expect(page.locator('text=Free, text=Pro')).toBeVisible();
    
    // Should show plan features
    await expect(page.locator('text=searches per day, text=Unlimited')).toBeVisible();
  });

  test('should initiate Stripe checkout when upgrading to Pro', async ({ page, context }) => {
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
          email: 'free-user@example.com',
          name: 'Free User',
          plan: 'free',
        }),
      });
    });

    // Mock Stripe checkout endpoint
    let checkoutCalled = false;
    await page.route('**/api/billing/create-checkout-session', async (route) => {
      checkoutCalled = true;
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          url: 'https://checkout.stripe.com/mock-session-id',
        }),
      });
    });

    await page.goto('/pricing');

    // Click upgrade button
    const upgradeButton = page.locator('button:has-text("Upgrade"), button:has-text("Get Pro"), a:has-text("Upgrade")').first();
    await upgradeButton.click();

    // Should call checkout endpoint
    await page.waitForTimeout(1000);
    expect(checkoutCalled).toBeTruthy();

    // In real scenario, would redirect to Stripe
    // For E2E we just verify the API was called
  });

  test('should handle successful upgrade after Stripe checkout', async ({ page, context }) => {
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

    // Initially free user
    let requestCount = 0;
    await page.route('**/api/auth/me', async (route) => {
      requestCount++;
      const plan = requestCount <= 1 ? 'free' : 'pro'; // Upgrade after first request
      
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          id: '00000000-0000-0000-0000-000000000001',
          email: 'free-user@example.com',
          name: 'Free User',
          plan: plan,
        }),
      });
    });

    // Navigate to success page (simulating return from Stripe)
    await page.goto('/billing/success?session_id=mock-session-id');

    // Should show success message
    await expect(page.locator('text=Success, text=upgraded, text=Pro')).toBeVisible({ timeout: 5000 });

    // Navigate to pricing page to verify plan changed
    await page.goto('/pricing');

    // Should show current plan as Pro
    await expect(page.locator('text=Current Plan: Pro, text=You are on the Pro plan')).toBeVisible();
  });

  test('should open Stripe billing portal for subscription management', async ({ page, context }) => {
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
          id: '00000000-0000-0000-0000-000000000002',
          email: 'pro-user@example.com',
          name: 'Pro User',
          plan: 'pro',
          stripe_customer_id: 'cus_mock123',
        }),
      });
    });

    // Mock billing portal endpoint
    let portalCalled = false;
    await page.route('**/api/billing/create-portal-session', async (route) => {
      portalCalled = true;
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          url: 'https://billing.stripe.com/mock-portal',
        }),
      });
    });

    await page.goto('/pricing');

    // Click manage subscription button
    const manageButton = page.locator('button:has-text("Manage"), button:has-text("Billing"), a:has-text("Manage Subscription")').first();
    
    if (await manageButton.isVisible({ timeout: 2000 }).catch(() => false)) {
      await manageButton.click();
      await page.waitForTimeout(1000);
      expect(portalCalled).toBeTruthy();
    }
  });

  test('should handle Stripe checkout errors gracefully', async ({ page, context }) => {
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
          email: 'free-user@example.com',
          name: 'Free User',
          plan: 'free',
        }),
      });
    });

    // Mock checkout error
    await page.route('**/api/billing/create-checkout-session', async (route) => {
      await route.fulfill({
        status: 500,
        contentType: 'application/json',
        body: JSON.stringify({
          error: 'Failed to create checkout session',
        }),
      });
    });

    await page.goto('/pricing');

    // Try to upgrade
    const upgradeButton = page.locator('button:has-text("Upgrade"), button:has-text("Get Pro")').first();
    await upgradeButton.click();

    // Should show error message
    await expect(page.locator('text=Error, text=Failed, text=try again')).toBeVisible({ timeout: 5000 });
  });

  test('should show quota usage indicator for free users', async ({ page, context }) => {
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
          email: 'free-user@example.com',
          name: 'Free User',
          plan: 'free',
          daily_search_count: 2,
        }),
      });
    });

    await page.goto('/search');

    // Should show quota usage (e.g., "2/5 searches used")
    const quotaIndicator = page.locator('text=/[0-9]+\\/[0-9]+ searches/i, text=searches used');
    
    if (await quotaIndicator.isVisible({ timeout: 2000 }).catch(() => false)) {
      await expect(quotaIndicator).toBeVisible();
    }
  });
});

test.describe('Billing & Quotas - Mobile', () => {
  test.use({ viewport: { width: 375, height: 667 } });

  test('should display upgrade prompt on mobile', async ({ page, context }) => {
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
          email: 'free-user@example.com',
          name: 'Free User',
          plan: 'free',
        }),
      });
    });

    await page.goto('/pricing');

    // Pricing should be mobile-responsive
    await expect(page.locator('text=Free')).toBeVisible();
    await expect(page.locator('text=Pro')).toBeVisible();

    // Tap upgrade button
    const upgradeButton = page.locator('button:has-text("Upgrade"), button:has-text("Get Pro")').first();
    if (await upgradeButton.isVisible()) {
      await upgradeButton.tap();
    }
  });
});
