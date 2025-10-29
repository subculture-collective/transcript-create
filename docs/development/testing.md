# Testing Guide

This guide covers testing practices, how to run tests, and how to write effective tests for Transcript Create.

## Table of Contents

- [Testing Philosophy](#testing-philosophy)
- [Test Types](#test-types)
- [Running Tests](#running-tests)
- [Writing Tests](#writing-tests)
- [Test Coverage](#test-coverage)
- [Testing Best Practices](#testing-best-practices)
- [Continuous Integration](#continuous-integration)

## Testing Philosophy

### Why We Test

- **Catch bugs early**: Find issues before they reach production
- **Enable refactoring**: Change code with confidence
- **Document behavior**: Tests serve as executable documentation
- **Prevent regressions**: Ensure fixes stay fixed

### Test Pyramid

We follow the testing pyramid principle:

```
        /\
       /  \      E2E Tests (Few)
      /____\     - Full user workflows
     /      \    - Browser automation
    /________\   Integration Tests (Some)
   /          \  - API + Database
  /____________\ - Multiple components
 /              \
/________________\ Unit Tests (Many)
                   - Individual functions
                   - Fast, isolated
```

## Test Types

### Unit Tests

**Purpose**: Test individual functions or methods in isolation

**Location**: 
- Backend: `tests/test_*.py`
- Frontend: `frontend/tests/*.test.tsx`

**Characteristics**:
- Fast (< 1 second per test)
- Isolated (no external dependencies)
- Focused (one behavior per test)

**Example**:
```python
# tests/test_audio.py
def test_chunk_audio_correct_count():
    """Test that audio is chunked into expected number of segments."""
    duration = 3600  # 1 hour
    chunk_seconds = 900  # 15 minutes
    
    chunks = calculate_chunk_count(duration, chunk_seconds)
    
    assert chunks == 4
```

### Integration Tests

**Purpose**: Test multiple components working together

**Location**: `tests/integration/test_*.py`

**Characteristics**:
- Slower (1-10 seconds per test)
- Use real database (PostgreSQL)
- Test complete workflows

**Example**:
```python
# tests/integration/test_job_flow.py
def test_create_and_process_job(db, api_client):
    """Test complete job creation and processing workflow."""
    # Create job
    response = api_client.post("/jobs", json={
        "url": "https://youtube.com/watch?v=test",
        "kind": "single"
    })
    assert response.status_code == 200
    job_id = response.json()["id"]
    
    # Verify job in database
    job = db.query(Job).filter(Job.id == job_id).first()
    assert job is not None
    assert job.state == "pending"
```

### End-to-End (E2E) Tests

**Purpose**: Test complete user workflows in a real browser

**Location**: `e2e/tests/*.spec.ts`

**Characteristics**:
- Slowest (10-60 seconds per test)
- Use real browser (Playwright)
- Test from user perspective

**Example**:
```typescript
// e2e/tests/search.spec.ts
test('search and view transcript', async ({ page }) => {
  await page.goto('/');
  
  // Search for video
  await page.fill('[data-testid="search-input"]', 'test query');
  await page.click('[data-testid="search-button"]');
  
  // Verify results
  await expect(page.locator('.search-result')).toHaveCount(1);
  
  // Click result
  await page.click('.search-result');
  
  // Verify transcript page
  await expect(page).toHaveURL(/\/videos\/\d+/);
  await expect(page.locator('.transcript-segment')).toBeVisible();
});
```

## Running Tests

### Backend Tests (pytest)

#### Basic Commands

```bash
# Run all tests
pytest

# Run with verbose output
pytest -v

# Run specific test file
pytest tests/test_crud.py

# Run specific test function
pytest tests/test_crud.py::test_create_job

# Run tests matching pattern
pytest -k "test_video"

# Run only integration tests
pytest tests/integration/

# Run with coverage
pytest --cov=app --cov=worker

# Generate HTML coverage report
pytest --cov=app --cov=worker --cov-report=html
open htmlcov/index.html  # View in browser
```

#### With Docker

```bash
# Run tests in Docker container
docker compose exec api pytest

# Run with coverage
docker compose exec api pytest --cov=app --cov=worker
```

#### Test Database Setup

Integration tests require a PostgreSQL database:

```bash
# Option 1: Use Docker Compose
docker compose up -d db

# Option 2: Local PostgreSQL
export DATABASE_URL="postgresql+psycopg://postgres:postgres@localhost:5432/postgres_test"

# Apply schema
python scripts/run_migrations.py upgrade
```

### Frontend Tests (Vitest)

```bash
cd frontend

# Run all tests
npm test

# Run in watch mode (auto-rerun on changes)
npm run test:watch

# Run with UI
npm run test:ui

# Run with coverage
npm run test:coverage

# Run specific test file
npm test -- SearchBar.test.tsx
```

### E2E Tests (Playwright)

```bash
cd e2e

# First time: install dependencies
npm install
npx playwright install --with-deps

# Start services (in separate terminals)
# Terminal 1: Backend
cd .. && uvicorn app.main:app --reload --port 8000

# Terminal 2: Frontend
cd frontend && npm run dev

# Terminal 3: Seed test database
cd e2e && npm run seed-db

# Run E2E tests
npm test                    # All tests
npm run test:headed        # With visible browser
npm run test:ui            # Interactive UI mode
npm run test:critical      # Fast critical tests only
npm run test:chromium      # Chromium only
npm run test:firefox       # Firefox only
npm run test:webkit        # Safari/WebKit only
npm run test:mobile        # Mobile viewports
```

## Writing Tests

### Backend Unit Tests

#### Structure

```python
# tests/test_module.py
import pytest
from app.module import function_to_test

def test_function_success_case():
    """Test that function works correctly with valid input."""
    # Arrange
    input_data = "test"
    
    # Act
    result = function_to_test(input_data)
    
    # Assert
    assert result == expected_output

def test_function_edge_case():
    """Test that function handles edge case."""
    # Test edge case
    pass

def test_function_error_case():
    """Test that function raises appropriate error."""
    with pytest.raises(ValueError, match="Invalid input"):
        function_to_test(invalid_input)
```

#### Using Fixtures

```python
# tests/conftest.py
import pytest
from app.db import engine
from sqlalchemy import text

@pytest.fixture
def db():
    """Provide database connection for tests."""
    with engine.begin() as conn:
        yield conn
        # Cleanup after test
        conn.execute(text("TRUNCATE TABLE videos CASCADE"))

@pytest.fixture
def sample_video(db):
    """Create a sample video for testing."""
    db.execute(text("""
        INSERT INTO videos (youtube_id, title, duration_seconds)
        VALUES ('test123', 'Test Video', 120)
    """))
    return {'youtube_id': 'test123', 'title': 'Test Video'}

# tests/test_videos.py
def test_get_video(db, sample_video):
    """Test fetching video by ID."""
    video = get_video_by_youtube_id(sample_video['youtube_id'])
    assert video.title == 'Test Video'
```

#### Mocking External Services

```python
from unittest.mock import patch, MagicMock

def test_download_audio_success(tmp_path):
    """Test audio download with mocked yt-dlp."""
    with patch('worker.audio.subprocess.run') as mock_run:
        mock_run.return_value = MagicMock(returncode=0)
        
        audio_path = download_audio("https://youtube.com/watch?v=test", tmp_path)
        
        assert mock_run.called
        assert audio_path.exists()
```

### Frontend Tests

#### Component Tests

```typescript
// frontend/tests/VideoPlayer.test.tsx
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { VideoPlayer } from '../src/components/VideoPlayer';
import { vi } from 'vitest';

describe('VideoPlayer', () => {
  it('renders video title', () => {
    const video = { id: 1, title: 'Test Video' };
    render(<VideoPlayer video={video} />);
    
    expect(screen.getByText('Test Video')).toBeInTheDocument();
  });

  it('plays video on button click', async () => {
    const onPlay = vi.fn();
    render(<VideoPlayer video={video} onPlay={onPlay} />);
    
    fireEvent.click(screen.getByRole('button', { name: /play/i }));
    
    await waitFor(() => {
      expect(onPlay).toHaveBeenCalledTimes(1);
    });
  });

  it('handles loading state', () => {
    render(<VideoPlayer video={null} />);
    
    expect(screen.getByText(/loading/i)).toBeInTheDocument();
  });
});
```

#### API Mocking

```typescript
// frontend/tests/api.test.ts
import { vi } from 'vitest';
import axios from 'axios';
import { fetchVideos } from '../src/api/videos';

vi.mock('axios');

describe('API Client', () => {
  it('fetches videos successfully', async () => {
    const mockVideos = [{ id: 1, title: 'Test' }];
    (axios.get as any).mockResolvedValue({ data: mockVideos });
    
    const videos = await fetchVideos();
    
    expect(videos).toEqual(mockVideos);
    expect(axios.get).toHaveBeenCalledWith('/api/videos');
  });

  it('handles API errors', async () => {
    (axios.get as any).mockRejectedValue(new Error('Network error'));
    
    await expect(fetchVideos()).rejects.toThrow('Network error');
  });
});
```

### E2E Tests

#### Page Object Pattern

```typescript
// e2e/pages/SearchPage.ts
export class SearchPage {
  constructor(private page: Page) {}

  async search(query: string) {
    await this.page.fill('[data-testid="search-input"]', query);
    await this.page.click('[data-testid="search-button"]');
  }

  async getResultCount() {
    return this.page.locator('.search-result').count();
  }

  async clickResult(index: number) {
    await this.page.locator('.search-result').nth(index).click();
  }
}

// e2e/tests/search.spec.ts
import { test, expect } from '@playwright/test';
import { SearchPage } from '../pages/SearchPage';

test('search returns results', async ({ page }) => {
  const searchPage = new SearchPage(page);
  
  await page.goto('/');
  await searchPage.search('test query');
  
  const count = await searchPage.getResultCount();
  expect(count).toBeGreaterThan(0);
});
```

## Test Coverage

### Checking Coverage

```bash
# Backend
pytest --cov=app --cov=worker --cov-report=term --cov-report=html

# Frontend
cd frontend && npm run test:coverage
```

### Coverage Goals

- **Overall**: Aim for 70%+ coverage
- **Critical paths**: 90%+ coverage
- **New code**: All new features should have tests
- **Bug fixes**: Add regression test

### Viewing Coverage Reports

```bash
# Backend HTML report
open htmlcov/index.html

# Frontend HTML report
open frontend/coverage/index.html
```

## Testing Best Practices

### General Principles

1. **Test behavior, not implementation**
   ```python
   # Good - tests behavior
   def test_user_can_favorite_video():
       response = api_client.post('/favorites', json={'video_id': 1})
       assert response.status_code == 200
       assert get_user_favorites(user_id) == [1]
   
   # Bad - tests implementation details
   def test_favorite_calls_database():
       with patch('app.crud.db.execute') as mock_execute:
           add_favorite(user_id, video_id)
           assert mock_execute.called
   ```

2. **Use descriptive test names**
   ```python
   # Good
   def test_search_returns_videos_matching_query():
       pass
   
   # Bad
   def test_search():
       pass
   ```

3. **One assertion per test** (when practical)
   ```python
   # Good - focused
   def test_video_title_required():
       with pytest.raises(ValidationError, match="title"):
           create_video(youtube_id="123", title=None)
   
   def test_video_duration_positive():
       with pytest.raises(ValidationError, match="duration"):
           create_video(youtube_id="123", title="Test", duration=-1)
   
   # Acceptable - related assertions
   def test_video_created_successfully():
       video = create_video(youtube_id="123", title="Test", duration=120)
       assert video.youtube_id == "123"
       assert video.title == "Test"
       assert video.duration == 120
   ```

4. **Clean up after tests**
   ```python
   @pytest.fixture
   def temp_file(tmp_path):
       file_path = tmp_path / "test.txt"
       file_path.write_text("test content")
       yield file_path
       # Cleanup happens automatically with tmp_path
   ```

5. **Mock external dependencies**
   - Mock API calls to external services
   - Mock file system operations when not testing I/O
   - Mock time-based operations for predictability

### Testing Async Code

```python
# Backend (pytest-asyncio)
import pytest

@pytest.mark.asyncio
async def test_async_function():
    result = await async_function()
    assert result == expected
```

```typescript
// Frontend (async/await in tests)
test('async operation', async () => {
  const result = await fetchData();
  expect(result).toBeDefined();
});
```

### Testing Error Cases

```python
def test_invalid_youtube_url():
    """Test that invalid URL raises appropriate error."""
    with pytest.raises(ValueError, match="Invalid YouTube URL"):
        validate_youtube_url("not-a-url")

def test_video_not_found():
    """Test 404 response for non-existent video."""
    response = api_client.get('/videos/99999')
    assert response.status_code == 404
    assert "not found" in response.json()["detail"].lower()
```

### Parameterized Tests

```python
@pytest.mark.parametrize("input,expected", [
    ("https://youtube.com/watch?v=abc", "abc"),
    ("https://www.youtube.com/watch?v=xyz", "xyz"),
    ("https://youtu.be/123", "123"),
])
def test_extract_video_id(input, expected):
    """Test video ID extraction from various URL formats."""
    assert extract_video_id(input) == expected
```

## Continuous Integration

### CI Test Pipeline

Our GitHub Actions workflows automatically run tests on every PR:

**Backend CI** (`backend-ci.yml`):
- Linting and formatting checks
- Type checking (mypy)
- Security scanning
- **Unit and integration tests with PostgreSQL**
- Coverage reporting

**Frontend CI** (`frontend-ci.yml`):
- Linting (ESLint)
- Type checking (TypeScript)
- **Unit tests (Vitest)**
- Build verification

**E2E Tests** (`e2e-tests.yml`):
- Playwright tests across browsers
- Mobile viewport tests
- Coverage: 255 tests

### Running CI Locally

```bash
# Backend checks (same as CI)
ruff check app/ worker/ scripts/
black --check app/ worker/ scripts/
isort --check-only app/ worker/
mypy app/ worker/
pytest tests/ --cov=app --cov=worker

# Frontend checks (same as CI)
cd frontend
npm run lint
npm run format:check
npx tsc --noEmit
npm test
npm run build
```

## Debugging Tests

### Backend

```bash
# Run single test with verbose output
pytest tests/test_crud.py::test_create_job -vv

# Drop into debugger on failure
pytest --pdb

# Show print statements
pytest -s

# Show local variables on failure
pytest -l
```

### Frontend

```bash
# Run tests in watch mode
npm run test:watch

# Run with UI for interactive debugging
npm run test:ui

# Debug specific test
npm test -- --grep "test name"
```

### E2E

```bash
# Run with visible browser
npm run test:headed

# Run with Playwright Inspector
PWDEBUG=1 npm test

# Run single test file
npm test -- search.spec.ts

# Generate trace for debugging failures
npm test -- --trace on
```

## Common Testing Patterns

### Testing Database Transactions

```python
def test_transaction_rollback_on_error(db):
    """Test that transaction rolls back on error."""
    try:
        with engine.begin() as conn:
            conn.execute(text("INSERT INTO videos ..."))
            raise Exception("Simulated error")
    except:
        pass
    
    # Verify rollback
    result = db.execute(text("SELECT COUNT(*) FROM videos"))
    assert result.scalar() == 0
```

### Testing Authentication

```python
def test_protected_route_requires_auth(api_client):
    """Test that protected route returns 401 without auth."""
    response = api_client.get('/admin/users')
    assert response.status_code == 401

def test_protected_route_allows_authenticated_user(api_client, auth_token):
    """Test that protected route works with valid auth."""
    headers = {'Authorization': f'Bearer {auth_token}'}
    response = api_client.get('/admin/users', headers=headers)
    assert response.status_code == 200
```

### Testing File Operations

```python
def test_file_cleanup(tmp_path):
    """Test that temporary files are cleaned up."""
    audio_file = tmp_path / "audio.wav"
    audio_file.write_bytes(b"fake audio data")
    
    process_and_cleanup(audio_file)
    
    assert not audio_file.exists()
```

## Resources

- **pytest documentation**: https://docs.pytest.org/
- **Vitest documentation**: https://vitest.dev/
- **Playwright documentation**: https://playwright.dev/
- **Testing Library**: https://testing-library.com/
- **Our E2E guide**: [../E2E-TESTING.md](../E2E-TESTING.md)

## Questions?

- Check existing tests for examples
- Ask in GitHub issues or discussions
- Review [CONTRIBUTING.md](../../CONTRIBUTING.md) for workflow

Happy testing! 🧪
