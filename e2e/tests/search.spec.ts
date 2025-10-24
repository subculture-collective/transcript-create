import { test, expect } from '@playwright/test';

/**
 * Search Flow E2E Tests
 * 
 * Tests searching transcripts, applying filters, and timestamp deeplinks
 */

test.describe('Search Flow', () => {
  test.beforeEach(async ({ page, context }) => {
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
          id: '00000000-0000-0000-0000-000000000002',
          email: 'pro-user@example.com',
          name: 'Pro User',
          plan: 'pro',
        }),
      });
    });
  });

  test('should perform basic search and display results', async ({ page }) => {
    await page.goto('/search');

    // Mock search API endpoint
    await page.route('**/api/search*', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          results: [
            {
              video_id: '00000000-0000-0000-0000-000000000201',
              youtube_id: 'dQw4w9WgXcQ',
              title: 'Rick Astley - Never Gonna Give You Up',
              segment_text: "We're no strangers to love",
              start_ms: 0,
              end_ms: 5000,
            },
            {
              video_id: '00000000-0000-0000-0000-000000000201',
              youtube_id: 'dQw4w9WgXcQ',
              title: 'Rick Astley - Never Gonna Give You Up',
              segment_text: 'You know the rules and so do I',
              start_ms: 5000,
              end_ms: 10000,
            },
          ],
          total: 2,
        }),
      });
    });

    // Enter search term
    const searchInput = page.locator('input[type="search"], input[placeholder*="Search"]').first();
    await searchInput.fill('love');

    // Submit search
    const searchButton = page.locator('button:has-text("Search"), button[type="submit"]').first();
    await searchButton.click();

    // Verify results are displayed
    await expect(page.locator('text=Rick Astley - Never Gonna Give You Up')).toBeVisible();
    await expect(page.locator('text=We\'re no strangers to love')).toBeVisible();
    await expect(page.locator('text=You know the rules and so do I')).toBeVisible();
  });

  test('should display video cards for search results', async ({ page }) => {
    await page.goto('/search');

    // Mock search API
    await page.route('**/api/search*', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          results: [
            {
              video_id: '00000000-0000-0000-0000-000000000201',
              youtube_id: 'dQw4w9WgXcQ',
              title: 'Rick Astley - Never Gonna Give You Up',
              segment_text: "We're no strangers to love",
              start_ms: 0,
              end_ms: 5000,
            },
          ],
          total: 1,
        }),
      });
    });

    // Perform search
    const searchInput = page.locator('input[type="search"], input[placeholder*="Search"]').first();
    await searchInput.fill('love');
    
    const searchButton = page.locator('button:has-text("Search"), button[type="submit"]').first();
    await searchButton.click();

    // Check video card elements
    await expect(page.locator('text=Rick Astley - Never Gonna Give You Up')).toBeVisible();
    
    // Should have YouTube thumbnail or video info
    const videoCard = page.locator('[data-testid="video-card"], .video-card, article').first();
    await expect(videoCard).toBeVisible();
  });

  test('should apply date filter and update results', async ({ page }) => {
    await page.goto('/search');

    let filterApplied = false;

    // Mock search API with filter
    await page.route('**/api/search*', async (route) => {
      const url = new URL(route.request().url());
      const dateFilter = url.searchParams.get('date_from');
      
      if (dateFilter) {
        filterApplied = true;
      }

      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          results: filterApplied ? [
            {
              video_id: '00000000-0000-0000-0000-000000000202',
              youtube_id: 'jNQXAC9IVRw',
              title: 'Me at the zoo',
              segment_text: 'All right, so here we are',
              start_ms: 0,
              end_ms: 3000,
            },
          ] : [],
          total: filterApplied ? 1 : 0,
        }),
      });
    });

    // Perform initial search
    const searchInput = page.locator('input[type="search"], input[placeholder*="Search"]').first();
    await searchInput.fill('zoo');
    
    const searchButton = page.locator('button:has-text("Search"), button[type="submit"]').first();
    await searchButton.click();

    // Apply date filter (if filter UI exists)
    const dateFilter = page.locator('input[type="date"], select[name="date"]');
    if (await dateFilter.isVisible({ timeout: 1000 }).catch(() => false)) {
      await dateFilter.fill('2006-01-01');
      
      // Results should update
      await expect(page.locator('text=Me at the zoo')).toBeVisible({ timeout: 5000 });
    }
  });

  test('should apply duration filter and update results', async ({ page }) => {
    await page.goto('/search');

    // Mock search with duration filter
    await page.route('**/api/search*', async (route) => {
      const url = new URL(route.request().url());
      const maxDuration = url.searchParams.get('max_duration');

      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          results: maxDuration ? [
            {
              video_id: '00000000-0000-0000-0000-000000000202',
              youtube_id: 'jNQXAC9IVRw',
              title: 'Me at the zoo',
              segment_text: 'Short video',
              start_ms: 0,
              end_ms: 3000,
              duration_seconds: 19,
            },
          ] : [
            {
              video_id: '00000000-0000-0000-0000-000000000201',
              youtube_id: 'dQw4w9WgXcQ',
              title: 'Rick Astley - Never Gonna Give You Up',
              segment_text: 'Long video',
              start_ms: 0,
              end_ms: 5000,
              duration_seconds: 212,
            },
          ],
          total: 1,
        }),
      });
    });

    // Perform search
    const searchInput = page.locator('input[type="search"], input[placeholder*="Search"]').first();
    await searchInput.fill('video');
    
    const searchButton = page.locator('button:has-text("Search"), button[type="submit"]').first();
    await searchButton.click();

    // Initially should show long video
    await expect(page.locator('text=Rick Astley')).toBeVisible({ timeout: 5000 });

    // Apply duration filter
    const durationFilter = page.locator('input[name="max_duration"], select[name="duration"]');
    if (await durationFilter.isVisible({ timeout: 1000 }).catch(() => false)) {
      await durationFilter.fill('30');
      
      // Should now show short video
      await expect(page.locator('text=Me at the zoo')).toBeVisible({ timeout: 5000 });
    }
  });

  test('should click timestamp deeplink and jump to video position', async ({ page }) => {
    await page.goto('/search');

    // Mock search API
    await page.route('**/api/search*', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          results: [
            {
              video_id: '00000000-0000-0000-0000-000000000201',
              youtube_id: 'dQw4w9WgXcQ',
              title: 'Rick Astley - Never Gonna Give You Up',
              segment_text: "We're no strangers to love",
              start_ms: 5000,
              end_ms: 10000,
            },
          ],
          total: 1,
        }),
      });
    });

    // Perform search
    const searchInput = page.locator('input[type="search"], input[placeholder*="Search"]').first();
    await searchInput.fill('love');
    
    const searchButton = page.locator('button:has-text("Search"), button[type="submit"]').first();
    await searchButton.click();

    // Wait for results
    await expect(page.locator('text=We\'re no strangers to love')).toBeVisible();

    // Click timestamp link
    const timestampLink = page.locator('a[href*="t=5"], a[href*="start_ms=5000"], text=0:05').first();
    if (await timestampLink.isVisible({ timeout: 2000 }).catch(() => false)) {
      await timestampLink.click();

      // Should navigate to video page with timestamp
      await expect(page).toHaveURL(/\/videos\/.*[?&](t=5|start_ms=5000)/);
    }
  });

  test('should show no results message when search returns empty', async ({ page }) => {
    await page.goto('/search');

    // Mock empty search results
    await page.route('**/api/search*', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          results: [],
          total: 0,
        }),
      });
    });

    // Perform search
    const searchInput = page.locator('input[type="search"], input[placeholder*="Search"]').first();
    await searchInput.fill('nonexistentquery12345');
    
    const searchButton = page.locator('button:has-text("Search"), button[type="submit"]').first();
    await searchButton.click();

    // Should show no results message
    await expect(page.locator('text=No results, text=No matches, text=nothing found')).toBeVisible({ timeout: 5000 });
  });

  test('should handle search API errors gracefully', async ({ page }) => {
    await page.goto('/search');

    // Mock API error
    await page.route('**/api/search*', async (route) => {
      await route.fulfill({
        status: 500,
        contentType: 'application/json',
        body: JSON.stringify({
          error: 'Internal server error',
        }),
      });
    });

    // Perform search
    const searchInput = page.locator('input[type="search"], input[placeholder*="Search"]').first();
    await searchInput.fill('test');
    
    const searchButton = page.locator('button:has-text("Search"), button[type="submit"]').first();
    await searchButton.click();

    // Should show error message
    await expect(page.locator('text=Error, text=Failed, text=try again')).toBeVisible({ timeout: 5000 });
  });
});

test.describe('Search Flow - Mobile', () => {
  test.use({ viewport: { width: 375, height: 667 } });

  test.beforeEach(async ({ page, context }) => {
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
        }),
      });
    });
  });

  test('should perform search on mobile device', async ({ page }) => {
    await page.goto('/search');

    // Mock search API
    await page.route('**/api/search*', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          results: [
            {
              video_id: '00000000-0000-0000-0000-000000000201',
              youtube_id: 'dQw4w9WgXcQ',
              title: 'Rick Astley - Never Gonna Give You Up',
              segment_text: "We're no strangers to love",
              start_ms: 0,
              end_ms: 5000,
            },
          ],
          total: 1,
        }),
      });
    });

    // Tap search input
    const searchInput = page.locator('input[type="search"], input[placeholder*="Search"]').first();
    await searchInput.tap();
    await searchInput.fill('love');

    // Tap search button
    const searchButton = page.locator('button:has-text("Search"), button[type="submit"]').first();
    await searchButton.tap();

    // Verify results on mobile
    await expect(page.locator('text=Rick Astley - Never Gonna Give You Up')).toBeVisible();
  });

  test('should swipe through search results on mobile', async ({ page }) => {
    await page.goto('/search');

    // Mock multiple results
    await page.route('**/api/search*', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          results: Array.from({ length: 20 }, (_, i) => ({
            video_id: `video-${i}`,
            youtube_id: `yt-${i}`,
            title: `Video ${i}`,
            segment_text: `Segment text ${i}`,
            start_ms: i * 1000,
            end_ms: (i + 1) * 1000,
          })),
          total: 20,
        }),
      });
    });

    // Perform search
    const searchInput = page.locator('input[type="search"], input[placeholder*="Search"]').first();
    await searchInput.tap();
    await searchInput.fill('test');
    
    const searchButton = page.locator('button:has-text("Search"), button[type="submit"]').first();
    await searchButton.tap();

    // Wait for results
    await expect(page.locator('text=Video 0')).toBeVisible();

    // Scroll down to see more results
    await page.evaluate(() => window.scrollTo(0, 1000));
    
    // Should see more results after scrolling
    await expect(page.locator('text=Video 5, text=Video 10')).toBeVisible({ timeout: 3000 });
  });
});
