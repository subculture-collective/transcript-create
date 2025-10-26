# E2E Testing Guide

This guide covers end-to-end (E2E) testing for the Transcript Create application using Playwright.

## Overview

Our E2E test suite validates complete user workflows across the entire stack (frontend, API, database). Tests run against real browsers and simulate actual user interactions.

## Table of Contents

- [Setup](#setup)
- [Running Tests](#running-tests)
- [Test Structure](#test-structure)
- [Writing Tests](#writing-tests)
- [Debugging](#debugging)
- [CI/CD Integration](#cicd-integration)
- [Best Practices](#best-practices)

## Setup

### Prerequisites

- Node.js 20 or later
- Python 3.11 or later
- PostgreSQL 16 or later
- Docker (optional, for running services)

### Installation

1. Install E2E dependencies:

```bash
cd e2e
npm install
npx playwright install --with-deps
```

2. Set up environment variables:

```bash
# Database connection for seeding test data
export DATABASE_URL="postgresql://postgres:postgres@localhost:5434/transcripts"

# Base URL for the frontend (optional, defaults to http://localhost:5173)
export PLAYWRIGHT_BASE_URL="http://localhost:5173"
```

3. Set up the database:

```bash
# Apply schema
PGPASSWORD=postgres psql -h localhost -U postgres -p 5434 -d transcripts -f ../sql/schema.sql

# Seed test data
npm run seed-db
```

## Running Tests

### Local Development

1. Start the backend API:

```bash
cd ..
uvicorn app.main:app --reload --port 8000
```

2. Start the frontend dev server:

```bash
cd frontend
npm run dev
```

3. Run E2E tests:

```bash
cd e2e

# Run all tests
npm test

# Run in headed mode (see browser)
npm run test:headed

# Run specific test file
npx playwright test tests/auth.spec.ts

# Run tests in a specific browser
npm run test:chromium
npm run test:firefox
npm run test:webkit

# Run mobile tests
npm run test:mobile

# Run only critical tests
npm run test:critical
```

### Debug Mode

Run tests in debug mode with Playwright Inspector:

```bash
npm run test:debug
```

Or debug a specific test:

```bash
npx playwright test tests/auth.spec.ts --debug
```

### UI Mode

Run tests in interactive UI mode:

```bash
npm run test:ui
```

This opens a GUI where you can:

- See all tests
- Run individual tests
- Watch tests execute
- Time-travel through test steps
- Inspect DOM snapshots

## Test Structure

```
e2e/
├── fixtures/              # Test data and utilities
│   ├── test-data.ts       # Sample test data (users, jobs, videos)
│   ├── db-seeder.ts       # Database seeding utility
│   └── seed-database.ts   # CLI script for seeding
├── tests/                 # Test specifications
│   ├── auth.spec.ts       # Authentication tests
│   ├── job-creation.spec.ts # Job creation tests
│   ├── search.spec.ts     # Search functionality tests
│   ├── export.spec.ts     # Export feature tests
│   ├── billing.spec.ts    # Billing and quota tests
│   └── error-handling.spec.ts # Error scenarios
├── playwright.config.ts   # Playwright configuration
├── package.json          # E2E dependencies
└── README.md            # This file
```

## Writing Tests

### Basic Test Structure

```typescript
import { test, expect } from '@playwright/test';

test.describe('Feature Name', () => {
  test.beforeEach(async ({ page, context }) => {
    // Setup: authenticate, mock APIs, etc.
  });

  test('should do something', async ({ page }) => {
    // Navigate
    await page.goto('/path');

    // Interact
    await page.locator('button').click();

    // Assert
    await expect(page.locator('text=Success')).toBeVisible();
  });
});
```

### Mocking API Responses

Mock API endpoints to control test data:

```typescript
await page.route('**/api/search*', async (route) => {
  await route.fulfill({
    status: 200,
    contentType: 'application/json',
    body: JSON.stringify({
      results: [/* test data */],
      total: 1,
    }),
  });
});
```

### Setting Up Authentication

```typescript
// Add session cookie
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

// Mock auth endpoint
await page.route('**/api/auth/me', async (route) => {
  await route.fulfill({
    status: 200,
    contentType: 'application/json',
    body: JSON.stringify({
      id: 'user-id',
      email: 'user@example.com',
      name: 'Test User',
      plan: 'free',
    }),
  });
});
```

### Mobile Testing

Test mobile viewports:

```typescript
test.describe('Mobile Tests', () => {
  test.use({ viewport: { width: 375, height: 667 } });

  test('should work on mobile', async ({ page }) => {
    await page.goto('/');
    // Use .tap() instead of .click() for mobile interactions
    await page.locator('button').tap();
  });
});
```

### Handling Downloads

Test file downloads:

```typescript
const downloadPromise = page.waitForEvent('download');
await page.locator('button:has-text("Download")').click();

const download = await downloadPromise;
expect(download.suggestedFilename()).toContain('.srt');

// Optionally verify file contents
const path = await download.path();
const content = fs.readFileSync(path, 'utf8');
expect(content).toContain('expected content');
```

## Debugging

### Common Issues

#### Tests Failing Locally

1. **Services not running**: Ensure API and frontend are running
2. **Database not seeded**: Run `npm run seed-db` in the e2e directory
3. **Port conflicts**: Check if ports 8000 (API) and 5173 (frontend) are available

#### Flaky Tests

1. **Timing issues**: Use proper waiting mechanisms:

   ```typescript
   // Good: Wait for element
   await expect(page.locator('text=Result')).toBeVisible();
   
   // Bad: Fixed timeout
   await page.waitForTimeout(1000); // Avoid unless necessary
   ```

2. **Network delays**: Increase timeouts for slow operations:

   ```typescript
   await expect(page.locator('text=Result')).toBeVisible({ timeout: 10000 });
   ```

3. **Race conditions**: Use proper selectors and wait for elements

### Debugging Tools

#### Playwright Inspector

Run tests with `--debug` to use the inspector:

```bash
npx playwright test --debug
```

Features:

- Step through tests
- Inspect element locators
- View console logs
- Record new tests

#### Trace Viewer

View traces for failed tests:

```bash
npx playwright show-trace test-results/path-to-trace.zip
```

Features:

- Timeline of test execution
- DOM snapshots at each step
- Network activity
- Console logs
- Screenshots

#### Screenshots and Videos

Configured to capture on failure:

- Screenshots: `test-results/*/screenshot.png`
- Videos: `test-results/*/video.webm`

View the HTML report:

```bash
npm run show-report
```

## CI/CD Integration

### GitHub Actions Workflow

Tests run automatically on:

- Pull requests (critical tests only)
- Push to main (full suite)
- Nightly schedule (full suite + mobile)
- Manual trigger

### Test Strategy

1. **Critical Tests on PRs**: Fast subset (~5-10 min)
   - Authentication
   - Job creation
   - Search

2. **Full Suite on Main**: All tests, multiple browsers (~20-30 min)
   - Chromium
   - Firefox
   - WebKit

3. **Nightly**: Full suite + mobile tests (~30-45 min)
   - All browsers
   - Mobile viewports

### Viewing CI Results

1. Go to the PR or commit in GitHub
2. Click "Details" on the E2E Tests check
3. View job logs and artifacts
4. Download Playwright report from artifacts

## Best Practices

### Do's ✅

1. **Use meaningful test descriptions**:

   ```typescript
   test('should show validation error for invalid YouTube URL', async ({ page }) => {
     // ...
   });
   ```

2. **Group related tests**:

   ```typescript
   test.describe('Authentication Flow', () => {
     // Related auth tests
   });
   ```

3. **Mock external services**: Don't depend on real YouTube API, Stripe, etc.

4. **Use data-testid for stable selectors**:

   ```typescript
   await page.locator('[data-testid="submit-button"]').click();
   ```

5. **Test user workflows, not implementation details**

6. **Clean up test data**: Use fixtures and cleanup hooks

7. **Run tests in parallel**: Playwright does this by default

8. **Use proper assertions**:

   ```typescript
   // Good
   await expect(page.locator('text=Success')).toBeVisible();
   
   // Bad
   expect(await page.locator('text=Success').isVisible()).toBe(true);
   ```

### Don'ts ❌

1. **Don't use fixed timeouts**: Use `waitForSelector`, `toBeVisible`, etc.

2. **Don't test implementation details**: Test user-facing behavior

3. **Don't make tests interdependent**: Each test should be independent

4. **Don't use real credentials**: Use test data and mocks

5. **Don't ignore flaky tests**: Fix them or mark as known issues

6. **Don't hardcode URLs**: Use configuration

7. **Don't write tests that are too specific**: They break easily

### Performance Tips

1. **Reuse authentication state**:

   ```typescript
   test.use({ storageState: 'auth.json' });
   ```

2. **Run tests in parallel**: Default with Playwright

3. **Use `test.skip()` for WIP tests**: Don't comment them out

4. **Optimize beforeEach**: Only set up what's needed

5. **Use shallow rendering when possible**: Mock deeply nested components

## Test Coverage Goals

- ✅ All critical user flows tested
- ✅ Authentication and authorization
- ✅ Job creation and processing
- ✅ Search functionality
- ✅ Export features
- ✅ Billing and quotas
- ✅ Error handling
- ✅ Mobile responsiveness
- ✅ Cross-browser compatibility

## Troubleshooting

### Database Connection Issues

```bash
# Check if PostgreSQL is running
psql -h localhost -U postgres -p 5434 -d transcripts -c "SELECT 1"

# Reset database
PGPASSWORD=postgres psql -h localhost -U postgres -p 5434 -d transcripts -f ../sql/schema.sql
cd e2e && npm run seed-db
```

### API Not Responding

```bash
# Check if API is running
curl http://localhost:8000/health

# Restart API
cd .. && uvicorn app.main:app --reload --port 8000
```

### Frontend Not Loading

```bash
# Check if frontend is running
curl http://localhost:5173

# Restart frontend
cd frontend && npm run dev
```

### Playwright Installation Issues

```bash
# Reinstall browsers
npx playwright install --with-deps

# Or install specific browser
npx playwright install --with-deps chromium
```

## Resources

- [Playwright Documentation](https://playwright.dev/)
- [Playwright Best Practices](https://playwright.dev/docs/best-practices)
- [Playwright API Reference](https://playwright.dev/docs/api/class-playwright)
- [Writing Tests Guide](https://playwright.dev/docs/writing-tests)
- [Debugging Guide](https://playwright.dev/docs/debug)

## Contributing

When adding new features:

1. Write E2E tests for critical user paths
2. Update this guide if introducing new patterns
3. Ensure tests pass locally before pushing
4. Keep tests fast and reliable
5. Document any special setup requirements

## Questions?

If you encounter issues or have questions:

1. Check this guide
2. Review existing tests for patterns
3. Check Playwright documentation
4. Ask in the team chat
5. Open an issue on GitHub
