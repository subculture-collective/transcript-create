import { test, expect } from '@playwright/test';

/**
 * Job Creation & Processing E2E Tests
 * 
 * Tests creating single video and channel jobs, monitoring progress,
 * and viewing completed transcripts
 */

test.describe('Job Creation & Processing', () => {
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
          id: '00000000-0000-0000-0000-000000000001',
          email: 'free-user@example.com',
          name: 'Free User',
          plan: 'free',
        }),
      });
    });
  });

  test('should create a single video job successfully', async ({ page }) => {
    // Navigate to job creation page (assuming there's a form on search or a dedicated page)
    await page.goto('/search');

    // Mock POST /api/jobs endpoint
    let jobCreated = false;
    await page.route('**/api/jobs', async (route) => {
      if (route.request().method() === 'POST') {
        jobCreated = true;
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({
            id: '00000000-0000-0000-0000-000000000999',
            user_id: '00000000-0000-0000-0000-000000000001',
            url: 'https://www.youtube.com/watch?v=dQw4w9WgXcQ',
            kind: 'single',
            state: 'pending',
            created_at: new Date().toISOString(),
          }),
        });
      } else {
        await route.continue();
      }
    });

    // Look for job creation form
    const urlInput = page.locator('input[type="text"], input[type="url"]').first();
    await urlInput.fill('https://www.youtube.com/watch?v=dQw4w9WgXcQ');

    // Submit the form
    const submitButton = page.locator('button:has-text("Create"), button:has-text("Submit"), button[type="submit"]').first();
    await submitButton.click();

    // Wait for job to be created
    await page.waitForTimeout(500);
    expect(jobCreated).toBeTruthy();

    // Should show success message or redirect to job detail
    await expect(
      page.locator('text=Job created, text=Success, text=Processing')
    ).toBeVisible({ timeout: 5000 });
  });

  test('should show job progress and poll for completion', async ({ page }) => {
    const jobId = '00000000-0000-0000-0000-000000000101';

    // Mock GET /api/jobs/:id endpoint with different states
    let requestCount = 0;
    await page.route(`**/api/jobs/${jobId}`, async (route) => {
      requestCount++;
      const state = requestCount <= 2 ? 'pending' : 'completed';
      
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          id: jobId,
          user_id: '00000000-0000-0000-0000-000000000001',
          url: 'https://www.youtube.com/watch?v=dQw4w9WgXcQ',
          kind: 'single',
          state: state,
          videos: state === 'completed' ? [{
            id: '00000000-0000-0000-0000-000000000201',
            youtube_id: 'dQw4w9WgXcQ',
            title: 'Rick Astley - Never Gonna Give You Up',
            state: 'completed',
          }] : [],
          created_at: new Date().toISOString(),
        }),
      });
    });

    // Navigate to job detail page
    await page.goto(`/jobs/${jobId}`);

    // Should show pending state initially
    await expect(page.locator('text=pending, text=Processing')).toBeVisible();

    // Wait for polling to complete
    await page.waitForTimeout(2000);

    // Should eventually show completed state
    await expect(page.locator('text=completed, text=Complete')).toBeVisible({ timeout: 10000 });
  });

  test('should create a channel job and expand to multiple videos', async ({ page }) => {
    await page.goto('/search');

    // Mock POST /api/jobs endpoint for channel
    await page.route('**/api/jobs', async (route) => {
      if (route.request().method() === 'POST') {
        const body = route.request().postDataJSON();
        if (body.kind === 'channel') {
          await route.fulfill({
            status: 200,
            contentType: 'application/json',
            body: JSON.stringify({
              id: '00000000-0000-0000-0000-000000000998',
              user_id: '00000000-0000-0000-0000-000000000001',
              url: 'https://www.youtube.com/@examplechannel',
              kind: 'channel',
              state: 'expanded',
              videos: [
                {
                  id: '00000000-0000-0000-0000-000000000301',
                  youtube_id: 'video1',
                  title: 'Video 1',
                  state: 'pending',
                },
                {
                  id: '00000000-0000-0000-0000-000000000302',
                  youtube_id: 'video2',
                  title: 'Video 2',
                  state: 'pending',
                },
              ],
              created_at: new Date().toISOString(),
            }),
          });
        }
      } else {
        await route.continue();
      }
    });

    // Enter channel URL
    const urlInput = page.locator('input[type="text"], input[type="url"]').first();
    await urlInput.fill('https://www.youtube.com/@examplechannel');

    // Select channel mode if there's a dropdown/radio
    const channelOption = page.locator('text=Channel, input[value="channel"]');
    if (await channelOption.isVisible({ timeout: 1000 }).catch(() => false)) {
      await channelOption.click();
    }

    // Submit
    const submitButton = page.locator('button:has-text("Create"), button:has-text("Submit"), button[type="submit"]').first();
    await submitButton.click();

    // Should show multiple videos in the job
    await expect(page.locator('text=Video 1')).toBeVisible({ timeout: 5000 });
    await expect(page.locator('text=Video 2')).toBeVisible({ timeout: 5000 });
  });

  test('should display transcript when video is completed', async ({ page }) => {
    const videoId = '00000000-0000-0000-0000-000000000201';

    // Mock GET /api/videos/:id/transcript endpoint
    await page.route(`**/api/videos/${videoId}/transcript`, async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          video_id: videoId,
          youtube_id: 'dQw4w9WgXcQ',
          title: 'Rick Astley - Never Gonna Give You Up',
          segments: [
            {
              start_ms: 0,
              end_ms: 5000,
              text: "We're no strangers to love",
            },
            {
              start_ms: 5000,
              end_ms: 10000,
              text: 'You know the rules and so do I',
            },
          ],
        }),
      });
    });

    // Navigate to video page
    await page.goto(`/videos/${videoId}`);

    // Should display transcript segments
    await expect(page.locator('text=We\'re no strangers to love')).toBeVisible();
    await expect(page.locator('text=You know the rules and so do I')).toBeVisible();
  });

  test('should handle invalid YouTube URL gracefully', async ({ page }) => {
    await page.goto('/search');

    // Mock POST /api/jobs endpoint to return error
    await page.route('**/api/jobs', async (route) => {
      if (route.request().method() === 'POST') {
        await route.fulfill({
          status: 400,
          contentType: 'application/json',
          body: JSON.stringify({
            error: 'Invalid YouTube URL',
          }),
        });
      }
    });

    // Enter invalid URL
    const urlInput = page.locator('input[type="text"], input[type="url"]').first();
    await urlInput.fill('https://not-youtube.com/video');

    // Submit
    const submitButton = page.locator('button:has-text("Create"), button:has-text("Submit"), button[type="submit"]').first();
    await submitButton.click();

    // Should show error message
    await expect(page.locator('text=Invalid YouTube URL, text=Error')).toBeVisible({ timeout: 5000 });
  });
});

test.describe('Job Creation - Mobile', () => {
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
          id: '00000000-0000-0000-0000-000000000001',
          email: 'free-user@example.com',
          name: 'Free User',
          plan: 'free',
        }),
      });
    });
  });

  test('should create job on mobile device', async ({ page }) => {
    await page.goto('/search');

    // Mock job creation
    await page.route('**/api/jobs', async (route) => {
      if (route.request().method() === 'POST') {
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({
            id: '00000000-0000-0000-0000-000000000999',
            state: 'pending',
          }),
        });
      }
    });

    // Fill form on mobile
    const urlInput = page.locator('input[type="text"], input[type="url"]').first();
    await urlInput.tap();
    await urlInput.fill('https://www.youtube.com/watch?v=dQw4w9WgXcQ');

    const submitButton = page.locator('button:has-text("Create"), button:has-text("Submit"), button[type="submit"]').first();
    await submitButton.tap();

    // Verify success
    await expect(page.locator('text=Job created, text=Success, text=Processing')).toBeVisible({ timeout: 5000 });
  });
});
