import { test, expect } from '@playwright/test';
import path from 'path';
import fs from 'fs';

/**
 * Export Flow E2E Tests
 * 
 * Tests exporting transcripts in various formats (SRT, VTT, PDF, JSON)
 */

test.describe('Export Flow', () => {
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

    // Mock video transcript endpoint
    await page.route('**/api/videos/*/transcript', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          video_id: '00000000-0000-0000-0000-000000000201',
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
  });

  test('should export transcript as SRT', async ({ page }) => {
    const videoId = '00000000-0000-0000-0000-000000000201';

    // Mock SRT export endpoint
    await page.route(`**/api/exports/videos/${videoId}/srt`, async (route) => {
      const srtContent = `1
00:00:00,000 --> 00:00:05,000
We're no strangers to love

2
00:00:05,000 --> 00:00:10,000
You know the rules and so do I
`;
      await route.fulfill({
        status: 200,
        contentType: 'text/plain',
        headers: {
          'Content-Disposition': 'attachment; filename="transcript.srt"',
        },
        body: srtContent,
      });
    });

    // Navigate to video page
    await page.goto(`/videos/${videoId}`);

    // Wait for page to load
    await expect(page.locator('text=Rick Astley')).toBeVisible();

    // Click Export button
    const exportButton = page.locator('button:has-text("Export"), button[aria-label="Export"]').first();
    await exportButton.click();

    // Select SRT format
    const srtOption = page.locator('text=SRT, button:has-text("SRT"), a:has-text("SRT")').first();
    
    // Setup download listener
    const downloadPromise = page.waitForEvent('download', { timeout: 10000 });
    await srtOption.click();

    // Wait for download
    const download = await downloadPromise;
    expect(download.suggestedFilename()).toContain('.srt');
  });

  test('should export transcript as VTT', async ({ page }) => {
    const videoId = '00000000-0000-0000-0000-000000000201';

    // Mock VTT export endpoint
    await page.route(`**/api/exports/videos/${videoId}/vtt`, async (route) => {
      const vttContent = `WEBVTT

00:00:00.000 --> 00:00:05.000
We're no strangers to love

00:00:05.000 --> 00:00:10.000
You know the rules and so do I
`;
      await route.fulfill({
        status: 200,
        contentType: 'text/vtt',
        headers: {
          'Content-Disposition': 'attachment; filename="transcript.vtt"',
        },
        body: vttContent,
      });
    });

    await page.goto(`/videos/${videoId}`);
    await expect(page.locator('text=Rick Astley')).toBeVisible();

    // Click Export button
    const exportButton = page.locator('button:has-text("Export"), button[aria-label="Export"]').first();
    await exportButton.click();

    // Select VTT format
    const vttOption = page.locator('text=VTT, button:has-text("VTT"), a:has-text("VTT")').first();
    
    const downloadPromise = page.waitForEvent('download', { timeout: 10000 });
    await vttOption.click();

    const download = await downloadPromise;
    expect(download.suggestedFilename()).toContain('.vtt');
  });

  test('should export transcript as PDF', async ({ page }) => {
    const videoId = '00000000-0000-0000-0000-000000000201';

    // Mock PDF export endpoint
    await page.route(`**/api/exports/videos/${videoId}/pdf`, async (route) => {
      // Simple PDF mock (in real scenario this would be actual PDF bytes)
      const pdfContent = Buffer.from('%PDF-1.4\n%Mock PDF content');
      await route.fulfill({
        status: 200,
        contentType: 'application/pdf',
        headers: {
          'Content-Disposition': 'attachment; filename="transcript.pdf"',
        },
        body: pdfContent,
      });
    });

    await page.goto(`/videos/${videoId}`);
    await expect(page.locator('text=Rick Astley')).toBeVisible();

    // Click Export button
    const exportButton = page.locator('button:has-text("Export"), button[aria-label="Export"]').first();
    await exportButton.click();

    // Select PDF format
    const pdfOption = page.locator('text=PDF, button:has-text("PDF"), a:has-text("PDF")').first();
    
    const downloadPromise = page.waitForEvent('download', { timeout: 10000 });
    await pdfOption.click();

    const download = await downloadPromise;
    expect(download.suggestedFilename()).toContain('.pdf');

    // Verify PDF is not corrupted (basic check)
    const downloadPath = await download.path();
    if (downloadPath) {
      const fileBuffer = fs.readFileSync(downloadPath);
      expect(fileBuffer.toString('utf8', 0, 4)).toBe('%PDF');
    }
  });

  test('should export transcript as JSON', async ({ page }) => {
    const videoId = '00000000-0000-0000-0000-000000000201';

    // Mock JSON export endpoint
    await page.route(`**/api/exports/videos/${videoId}/json`, async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        headers: {
          'Content-Disposition': 'attachment; filename="transcript.json"',
        },
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

    await page.goto(`/videos/${videoId}`);
    await expect(page.locator('text=Rick Astley')).toBeVisible();

    // Click Export button
    const exportButton = page.locator('button:has-text("Export"), button[aria-label="Export"]').first();
    await exportButton.click();

    // Select JSON format
    const jsonOption = page.locator('text=JSON, button:has-text("JSON"), a:has-text("JSON")').first();
    
    const downloadPromise = page.waitForEvent('download', { timeout: 10000 });
    await jsonOption.click();

    const download = await downloadPromise;
    expect(download.suggestedFilename()).toContain('.json');

    // Verify JSON is valid
    const downloadPath = await download.path();
    if (downloadPath) {
      const fileContent = fs.readFileSync(downloadPath, 'utf8');
      const json = JSON.parse(fileContent);
      expect(json.video_id).toBe(videoId);
      expect(json.segments).toHaveLength(2);
    }
  });

  test('should show export menu with all available formats', async ({ page }) => {
    const videoId = '00000000-0000-0000-0000-000000000201';
    
    await page.goto(`/videos/${videoId}`);
    await expect(page.locator('text=Rick Astley')).toBeVisible();

    // Click Export button
    const exportButton = page.locator('button:has-text("Export"), button[aria-label="Export"]').first();
    await exportButton.click();

    // Verify all export options are available
    await expect(page.locator('text=SRT')).toBeVisible();
    await expect(page.locator('text=VTT')).toBeVisible();
    await expect(page.locator('text=PDF')).toBeVisible();
    await expect(page.locator('text=JSON')).toBeVisible();
  });

  test('should handle export API errors gracefully', async ({ page }) => {
    const videoId = '00000000-0000-0000-0000-000000000201';

    // Mock export endpoint with error
    await page.route(`**/api/exports/videos/${videoId}/srt`, async (route) => {
      await route.fulfill({
        status: 500,
        contentType: 'application/json',
        body: JSON.stringify({
          error: 'Export failed',
        }),
      });
    });

    await page.goto(`/videos/${videoId}`);
    await expect(page.locator('text=Rick Astley')).toBeVisible();

    // Click Export button
    const exportButton = page.locator('button:has-text("Export"), button[aria-label="Export"]').first();
    await exportButton.click();

    // Try to export
    const srtOption = page.locator('text=SRT, button:has-text("SRT"), a:has-text("SRT")').first();
    await srtOption.click();

    // Should show error message
    await expect(page.locator('text=Export failed, text=Error, text=try again')).toBeVisible({ timeout: 5000 });
  });

  test('should disable export for videos without transcripts', async ({ page }) => {
    const videoId = '00000000-0000-0000-0000-000000000999';

    // Mock video without transcript
    await page.route(`**/api/videos/${videoId}/transcript`, async (route) => {
      await route.fulfill({
        status: 404,
        contentType: 'application/json',
        body: JSON.stringify({
          error: 'Transcript not found',
        }),
      });
    });

    await page.goto(`/videos/${videoId}`);

    // Export button should be disabled or not visible
    const exportButton = page.locator('button:has-text("Export"), button[aria-label="Export"]');
    
    if (await exportButton.isVisible({ timeout: 2000 }).catch(() => false)) {
      // If visible, it should be disabled
      await expect(exportButton).toBeDisabled();
    }
  });
});

test.describe('Export Flow - Mobile', () => {
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

    await page.route('**/api/videos/*/transcript', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          video_id: '00000000-0000-0000-0000-000000000201',
          youtube_id: 'dQw4w9WgXcQ',
          title: 'Rick Astley - Never Gonna Give You Up',
          segments: [
            { start_ms: 0, end_ms: 5000, text: "We're no strangers to love" },
          ],
        }),
      });
    });
  });

  test('should export on mobile device', async ({ page }) => {
    const videoId = '00000000-0000-0000-0000-000000000201';

    await page.route(`**/api/exports/videos/${videoId}/srt`, async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'text/plain',
        headers: {
          'Content-Disposition': 'attachment; filename="transcript.srt"',
        },
        body: '1\n00:00:00,000 --> 00:00:05,000\nTest',
      });
    });

    await page.goto(`/videos/${videoId}`);

    // Tap Export button
    const exportButton = page.locator('button:has-text("Export"), button[aria-label="Export"]').first();
    await exportButton.tap();

    // Tap SRT option
    const srtOption = page.locator('text=SRT, button:has-text("SRT")').first();
    
    const downloadPromise = page.waitForEvent('download', { timeout: 10000 });
    await srtOption.tap();

    const download = await downloadPromise;
    expect(download.suggestedFilename()).toContain('.srt');
  });
});
