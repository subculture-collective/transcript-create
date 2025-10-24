# E2E Testing Quick Reference

Quick reference guide for running and working with E2E tests in Transcript Create.

## Quick Start

```bash
# Navigate to e2e directory
cd e2e

# Install dependencies (first time only)
npm install
npx playwright install --with-deps

# Start services (in separate terminals)
cd .. && uvicorn app.main:app --reload --port 8000  # Backend
cd frontend && npm run dev                          # Frontend

# Seed database
cd e2e && npm run seed-db

# Run tests
npm test
```

## Common Commands

```bash
# Run all tests
npm test

# Run in headed mode (see browser)
npm run test:headed

# Run with UI mode (interactive)
npm run test:ui

# Run in debug mode
npm run test:debug

# Run specific browser
npm run test:chromium
npm run test:firefox
npm run test:webkit

# Run mobile tests only
npm run test:mobile

# Run critical tests (fast)
npm run test:critical

# Run specific test file
npx playwright test tests/auth.spec.ts

# Run specific test by name
npx playwright test -g "should login"

# View test report
npm run show-report
```

## Test File Structure

```
tests/
├── auth.spec.ts          # Authentication & sessions
├── job-creation.spec.ts  # Creating jobs, viewing progress
├── search.spec.ts        # Search, filters, deeplinks
├── export.spec.ts        # Export SRT, VTT, PDF, JSON
├── billing.spec.ts       # Quotas, upgrades, Stripe
└── error-handling.spec.ts # 404s, errors, edge cases
```

## Writing Tests Checklist

- [ ] Import `test` and `expect` from `@playwright/test`
- [ ] Group tests with `test.describe()`
- [ ] Set up authentication in `beforeEach()` if needed
- [ ] Mock API endpoints with `page.route()`
- [ ] Use proper waiting: `await expect().toBeVisible()`
- [ ] Add meaningful test descriptions
- [ ] Test both success and error cases
- [ ] Clean up resources in `afterEach()` if needed

## Test Template

```typescript
import { test, expect } from '@playwright/test';

test.describe('Feature Name', () => {
  test.beforeEach(async ({ page, context }) => {
    // Setup authentication
    await context.addCookies([...]);
    
    // Mock APIs
    await page.route('**/api/endpoint', async (route) => {
      await route.fulfill({ status: 200, body: '...' });
    });
  });

  test('should do something', async ({ page }) => {
    await page.goto('/path');
    await page.locator('button').click();
    await expect(page.locator('text=Success')).toBeVisible();
  });
});
```

## Debugging Tips

### Test Failing?

1. **Run in headed mode**: `npm run test:headed`
2. **Use debug mode**: `npm run test:debug`
3. **Check screenshots**: `test-results/*/screenshot.png`
4. **Watch videos**: `test-results/*/video.webm`
5. **View HTML report**: `npm run show-report`

### Services Not Running?

```bash
# Check API
curl http://localhost:8000/health

# Check frontend
curl http://localhost:5173

# Check database
psql -h localhost -U postgres -p 5434 -d transcripts -c "SELECT 1"
```

### Database Issues?

```bash
# Re-apply schema
PGPASSWORD=postgres psql -h localhost -U postgres -p 5434 -d transcripts -f sql/schema.sql

# Re-seed data
cd e2e && npm run seed-db clean && npm run seed-db
```

## Useful Selectors

```typescript
// By text
page.locator('text=Login')
page.locator('button:has-text("Submit")')

// By role
page.locator('button[type="submit"]')
page.locator('input[type="email"]')

// By test ID (preferred for stability)
page.locator('[data-testid="login-button"]')

// CSS selectors
page.locator('.btn-primary')
page.locator('#user-menu')

// Multiple conditions
page.locator('button:has-text("Login"), a:has-text("Login")')
```

## Mobile Testing

```typescript
test.describe('Mobile Tests', () => {
  test.use({ viewport: { width: 375, height: 667 } });

  test('works on mobile', async ({ page }) => {
    await page.goto('/');
    await page.locator('button').tap(); // Use tap() for mobile
  });
});
```

## Mocking APIs

```typescript
// Mock successful response
await page.route('**/api/search*', async (route) => {
  await route.fulfill({
    status: 200,
    contentType: 'application/json',
    body: JSON.stringify({ results: [...] }),
  });
});

// Mock error response
await page.route('**/api/jobs', async (route) => {
  await route.fulfill({
    status: 400,
    body: JSON.stringify({ error: 'Invalid URL' }),
  });
});

// Mock network failure
await page.route('**/api/search*', async (route) => {
  await route.abort('failed');
});
```

## Test Assertions

```typescript
// Visibility
await expect(page.locator('text=Success')).toBeVisible();
await expect(page.locator('text=Error')).not.toBeVisible();

// Text content
await expect(page.locator('h1')).toHaveText('Welcome');
await expect(page.locator('p')).toContainText('partial');

// URL
await expect(page).toHaveURL('/dashboard');
await expect(page).toHaveURL(/\/videos\/.+/);

// Attributes
await expect(page.locator('button')).toBeEnabled();
await expect(page.locator('button')).toBeDisabled();
await expect(page.locator('input')).toHaveValue('test');

// Count
await expect(page.locator('.item')).toHaveCount(5);
```

## CI/CD

Tests run automatically on:
- **Pull Requests**: Critical tests (auth, job creation, search)
- **Main Branch**: Full suite (all browsers)
- **Nightly**: Full suite + mobile tests

View results:
1. Go to PR or commit in GitHub
2. Click "Details" on E2E Tests check
3. Download artifacts for screenshots/videos

## Environment Variables

```bash
# Database connection
export DATABASE_URL="postgresql://postgres:postgres@localhost:5434/transcripts"

# Frontend base URL
export PLAYWRIGHT_BASE_URL="http://localhost:5173"

# Run in CI mode
export CI=true
```

## Performance

- Tests run in parallel by default (4-8 workers)
- Critical tests: ~5-10 minutes
- Full suite: ~20-30 minutes
- Mobile tests: +10 minutes

## Best Practices

✅ **Do:**
- Use data-testid for stable selectors
- Mock external services (YouTube, Stripe)
- Test user workflows, not implementation
- Keep tests independent
- Use proper waiting mechanisms

❌ **Don't:**
- Use fixed timeouts (await page.waitForTimeout())
- Depend on test execution order
- Test implementation details
- Hardcode sensitive data
- Ignore flaky tests

## Getting Help

1. Check [e2e/README.md](../e2e/README.md) for detailed guide
2. Review [Playwright docs](https://playwright.dev/)
3. Check existing tests for patterns
4. Ask in team chat
5. Open GitHub issue

## Troubleshooting Checklist

- [ ] Services are running (API on 8000, frontend on 5173)
- [ ] Database is accessible and seeded
- [ ] Playwright browsers are installed
- [ ] No port conflicts
- [ ] Environment variables are set
- [ ] Dependencies are installed (`npm ci`)
- [ ] Test syntax is valid (`npx tsc --noEmit`)

## File Locations

- Tests: `/e2e/tests/*.spec.ts`
- Config: `/e2e/playwright.config.ts`
- Fixtures: `/e2e/fixtures/`
- Results: `/e2e/test-results/`
- Report: `/e2e/playwright-report/`
- Documentation: `/e2e/README.md`

## Additional Resources

- [Full E2E Testing Guide](../e2e/README.md)
- [Playwright Documentation](https://playwright.dev/)
- [Playwright API Reference](https://playwright.dev/docs/api/class-playwright)
- [GitHub Actions Workflow](../.github/workflows/e2e-tests.yml)
