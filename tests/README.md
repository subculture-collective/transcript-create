# Backend Unit Tests

This directory contains comprehensive unit tests for the FastAPI backend application.

## Test Structure

### Test Files

- `conftest.py` - Pytest configuration and shared fixtures (database, test client)
- `test_smoke.py` - Basic smoke tests to verify application starts
- `test_settings.py` - Settings and configuration tests
- `test_conftest_exceptions.py` - Tests for conftest exception handling
- `test_crud.py` - CRUD operation tests (database layer)
- `test_routes_jobs.py` - Job creation and retrieval endpoint tests
- `test_routes_videos.py` - Video and transcript endpoint tests
- `test_routes_search.py` - Search functionality tests (Postgres FTS and OpenSearch)
- `test_routes_auth.py` - Authentication and session management tests
- `test_routes_billing.py` - Stripe billing integration tests (mocked)
- `test_routes_exports.py` - Export functionality tests (SRT, VTT, JSON, PDF)
- `test_schemas.py` - Pydantic model validation tests

## Running Tests

### Prerequisites

1. Install test dependencies:
   ```bash
   pip install -r requirements-dev.txt
   pip install -r requirements.txt
   ```

2. Set up a PostgreSQL test database:
   ```bash
   # Using Docker
   docker run --name test-postgres -e POSTGRES_PASSWORD=postgres -p 5432:5432 -d postgres:15
   
   # Apply schema
   psql postgresql://postgres:postgres@localhost:5432/postgres -f sql/schema.sql
   ```

### Run All Tests

```bash
# Basic test run
pytest tests/

# With verbose output
pytest tests/ -v

# With coverage
pytest tests/ --cov=app --cov-report=term --cov-report=html

# Run specific test file
pytest tests/test_routes_jobs.py -v

# Run specific test
pytest tests/test_routes_jobs.py::TestJobsRoutes::test_create_job_single_success -v
```

### Environment Variables

Tests require the following environment variables:

```bash
export DATABASE_URL="postgresql://postgres:postgres@localhost:5432/postgres"
export SESSION_SECRET="test-secret-key"
export FRONTEND_ORIGIN="http://localhost:5173"
```

## Test Fixtures

### Database Fixtures

- `test_database_url` - Returns test database URL from environment
- `test_engine` - Creates SQLAlchemy engine for tests
- `db_session` - Provides isolated database session with automatic rollback
- `setup_test_database` - Ensures database schema is initialized

### Application Fixtures

- `client` - FastAPI TestClient for making HTTP requests

## Test Coverage Goals

- **Target**: 70%+ code coverage on `app/` directory
- **Critical paths**: All happy paths and error cases covered
- **Mocking**: External dependencies (OAuth, Stripe, OpenSearch) are properly mocked

## Writing New Tests

### Test Class Pattern

```python
class TestMyFeature:
    """Tests for my feature."""
    
    def test_happy_path(self, client: TestClient):
        """Test the successful case."""
        response = client.get("/my-endpoint")
        assert response.status_code == 200
    
    def test_error_case(self, client: TestClient):
        """Test error handling."""
        response = client.get("/my-endpoint?invalid=param")
        assert response.status_code == 400
```

### Using Database Fixtures

```python
def test_with_database(self, client: TestClient, db_session):
    """Test that requires database access."""
    # Create test data
    db_session.execute(text("INSERT INTO ..."))
    db_session.commit()
    
    # Test endpoint
    response = client.get("/endpoint")
    assert response.status_code == 200
```

### Mocking External Services

```python
from unittest.mock import patch, MagicMock

@patch("stripe.checkout.Session.create")
def test_stripe_integration(self, mock_stripe, client):
    """Test Stripe integration with mocking."""
    mock_stripe.return_value = MagicMock(id="cs_test", url="https://...")
    response = client.post("/billing/checkout-session", json={})
    assert response.status_code == 200
```

## CI Integration

Tests run automatically in GitHub Actions on:
- Push to `main` branch
- Pull requests
- Manual workflow dispatch

The CI pipeline:
1. Sets up Python 3.11 and 3.12
2. Installs dependencies
3. Starts PostgreSQL service
4. Applies database schema
5. Runs tests with coverage
6. Generates coverage reports
7. Uploads artifacts

## Troubleshooting

### Database Connection Errors

If you see "OperationalError: could not connect to server":
- Ensure PostgreSQL is running
- Check DATABASE_URL environment variable
- Verify PostgreSQL is listening on port 5432

### Schema Errors

If you see "ProgrammingError: relation does not exist":
- Apply the database schema: `psql $DATABASE_URL -f sql/schema.sql`
- The test fixture handles missing schema gracefully in CI

### Import Errors

If you see "ModuleNotFoundError":
- Ensure you're in the repository root directory
- Install all dependencies: `pip install -r requirements.txt -r requirements-dev.txt`

## Coverage Reports

After running tests with coverage, view the HTML report:

```bash
# Generate and open HTML coverage report
pytest tests/ --cov=app --cov-report=html
open htmlcov/index.html  # macOS
xdg-open htmlcov/index.html  # Linux
```

## Best Practices

1. **Test names**: Use descriptive names following `test_<action>_<expected_result>` pattern
2. **Isolation**: Each test should be independent and not rely on other tests
3. **Fixtures**: Use fixtures for common setup to avoid code duplication
4. **Mocking**: Mock external services to avoid network calls and improve speed
5. **Assertions**: Use specific assertions with clear error messages
6. **Documentation**: Add docstrings to test classes and methods

## References

- [FastAPI Testing Documentation](https://fastapi.tiangolo.com/tutorial/testing/)
- [Pytest Documentation](https://docs.pytest.org/)
- [pytest-asyncio](https://github.com/pytest-dev/pytest-asyncio)
- [Coverage.py](https://coverage.readthedocs.io/)
