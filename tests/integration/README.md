# Integration Tests

This directory contains comprehensive end-to-end integration tests for the transcript-create application.

## Overview

Integration tests validate complete workflows from job creation to export, ensuring all components work together correctly.

## Test Categories

### Job Processing Flow
- **test_job_flow.py**: Tests for job creation, status polling, and concurrent operations
  - Single video job creation
  - Channel job creation
  - Job status retrieval
  - Concurrent job creation
  - Error handling for invalid URLs

### Video & Transcript Flow
- **test_video_flow.py**: Tests for video and transcript workflows
  - Video transcript retrieval
  - Segment ordering and formatting
  - State transitions
  - Database integrity checks

### Export Flow
- **test_export_flow.py**: Tests for export functionality
  - SRT format export
  - PDF format export
  - Empty transcript handling
  - Timestamp format validation

### Search Flow
- **test_search_flow.py**: Tests for search functionality
  - Native transcript search
  - YouTube caption search
  - Search filters and pagination
  - Performance validation

### Worker Flow
- **test_worker_flow.py**: Tests for worker processing
  - Video picking with SKIP LOCKED
  - Job expansion (single and channel)
  - State transitions
  - Error handling
  - Large channel processing

### Auth Flow
- **test_auth_flow.py**: Tests for authentication and authorization
  - OAuth login (mocked)
  - Session management
  - Protected endpoint access
  - Quota enforcement

### Billing Flow
- **test_billing_flow.py**: Tests for billing and payments
  - Stripe checkout sessions (mocked)
  - Webhook handling
  - Plan upgrades/downgrades
  - Payment method management

## Running Tests

### Prerequisites

1. Install dependencies:
   ```bash
   pip install -r requirements-dev.txt
   pip install -r requirements.txt
   ```

2. Set up PostgreSQL:
   ```bash
   # Using Docker
   docker compose up -d db migrations
   
   # Or using local PostgreSQL
   createdb transcripts
   psql transcripts < sql/schema.sql
   ```

3. Set environment variables:
   ```bash
   export DATABASE_URL=postgresql://postgres:postgres@localhost:5432/postgres
   export SESSION_SECRET=test-secret-key
   export FRONTEND_ORIGIN=http://localhost:5173
   ```

### Run All Integration Tests

```bash
pytest tests/integration/ -v
```

### Run Specific Test File

```bash
pytest tests/integration/test_job_flow.py -v
```

### Run Specific Test

```bash
pytest tests/integration/test_job_flow.py::TestJobProcessingFlow::test_create_job_single_video -v
```

### Run with Coverage

```bash
pytest tests/integration/ --cov=app --cov-report=html
```

### Run with Timeouts

```bash
pytest tests/integration/ --timeout=120 -v
```

### Run in Parallel (faster)

```bash
pytest tests/integration/ -n auto
```

## Test Configuration

### Timeouts

Each test has a timeout decorator (default 60-120 seconds) to prevent hanging tests:

```python
@pytest.mark.timeout(60)
def test_example():
    pass
```

### Database Cleanup

Tests use the `clean_test_data` fixture to ensure a clean database state:

```python
def test_example(integration_client, integration_db, clean_test_data):
    # Database is clean at start
    # Automatically cleaned up after test
    pass
```

### Test Isolation

Each test runs in its own transaction that is rolled back, ensuring test isolation.

## Fixtures

### Standard Fixtures

- `integration_client`: FastAPI TestClient for API requests
- `integration_db`: Database session with automatic cleanup
- `clean_test_data`: Cleans test data before and after each test
- `wait_for_job_completion`: Helper to poll for job completion
- `wait_for_video_completion`: Helper to poll for video completion

### Data Fixtures

- `mock_youtube_video`: Sample YouTube video metadata
- `mock_youtube_channel`: Sample YouTube channel metadata
- `sample_transcript_segments`: Sample transcript segments

## CI Integration

Integration tests run automatically on:
- Every pull request
- Push to main branch
- Nightly (full test suite)
- Manual workflow dispatch

See `.github/workflows/integration-tests.yml` for CI configuration.

## Performance Targets

- API response time: < 500ms for GET requests
- Test execution: < 15 minutes total
- Individual test timeout: 60-120 seconds
- Pass rate: > 95%

## Debugging Failed Tests

### View Test Output

```bash
pytest tests/integration/ -v --tb=short
```

### Run Failed Tests Only

```bash
pytest tests/integration/ --lf
```

### Debug Mode

```bash
pytest tests/integration/ -vv -s --pdb
```

### Check Database State

```bash
psql $DATABASE_URL -c "SELECT * FROM jobs;"
psql $DATABASE_URL -c "SELECT * FROM videos;"
```

### View Logs

Check logs in `/tmp/*.log` or docker logs:
```bash
docker compose logs api
docker compose logs worker
```

## Writing New Integration Tests

### Test Structure

```python
import pytest
from fastapi.testclient import TestClient

class TestNewFeature:
    """Integration tests for new feature."""
    
    @pytest.mark.timeout(60)
    def test_feature_works(self, integration_client: TestClient, clean_test_data):
        """Test that feature works correctly."""
        # Arrange
        # ... setup test data
        
        # Act
        response = integration_client.post("/endpoint", json={...})
        
        # Assert
        assert response.status_code == 200
        assert response.json()["key"] == "expected"
```

### Best Practices

1. **Use descriptive test names**: `test_create_job_single_video` not `test_job1`
2. **Test one thing**: Each test should validate one behavior
3. **Clean up**: Use fixtures for cleanup, don't rely on test order
4. **Handle missing features**: Use `pytest.skip()` for unimplemented features
5. **Mock external services**: Don't make real API calls to YouTube, Stripe, etc.
6. **Add timeouts**: All tests should have timeout decorators
7. **Document edge cases**: Add tests for error conditions and edge cases

### Example: Adding a New Test

```python
@pytest.mark.timeout(60)
def test_new_feature(self, integration_client, integration_db, clean_test_data):
    """Test description."""
    # Create test data
    job_id = uuid.uuid4()
    integration_db.execute(
        text("INSERT INTO jobs (id, kind, state, input_url) VALUES (:id, 'single', 'pending', 'url')"),
        {"id": str(job_id)}
    )
    integration_db.commit()
    
    # Test the feature
    response = integration_client.get(f"/endpoint/{job_id}")
    assert response.status_code == 200
```

## Known Limitations

1. **Worker tests**: Some worker tests require actual worker process running
2. **Auth tests**: OAuth flows are mocked, not fully integrated
3. **Billing tests**: Stripe webhooks are mocked
4. **Search tests**: OpenSearch might not be running in all test environments
5. **Media files**: No actual audio/video processing in tests (mocked)

## Troubleshooting

### Database Connection Errors

Ensure PostgreSQL is running and DATABASE_URL is correct:
```bash
psql $DATABASE_URL -c "SELECT 1"
```

### Import Errors

Install all dependencies:
```bash
pip install -r requirements.txt -r requirements-dev.txt
```

### Timeout Errors

Increase timeout or run tests individually:
```bash
pytest tests/integration/test_slow.py --timeout=300
```

### Permission Errors

Check database permissions:
```bash
psql $DATABASE_URL -c "GRANT ALL PRIVILEGES ON DATABASE postgres TO postgres;"
```

## Contributing

When adding new features, please add corresponding integration tests:

1. Add test file to `tests/integration/`
2. Use existing fixtures and patterns
3. Add documentation to this README
4. Ensure tests pass in CI
5. Verify test coverage remains high

## Support

For questions or issues with integration tests:
- Check existing tests for examples
- Review test output and logs
- Ask in pull request or issue comments
