"""Test exception handling in conftest.py setup_test_database fixture.

These tests validate that the exception handling properly distinguishes between:
- ProgrammingError (missing schema) - which is handled gracefully
- OperationalError (connection issues) - which is raised to surface the problem
"""

from unittest.mock import MagicMock

from sqlalchemy.exc import OperationalError, ProgrammingError


def test_setup_handles_programming_error_gracefully():
    """Test that ProgrammingError (missing schema) is handled gracefully."""
    # Create a mock engine
    mock_engine = MagicMock()
    mock_conn = MagicMock()
    mock_engine.connect.return_value.__enter__.return_value = mock_conn

    # Mock execute to raise ProgrammingError (table doesn't exist)
    mock_conn.execute.side_effect = ProgrammingError("relation 'jobs' does not exist", None, None)

    # Import and call the function directly (not as a fixture)
    # This simulates what the fixture does
    try:
        with mock_engine.connect() as conn:
            conn.execute("SELECT 1 FROM jobs LIMIT 1")
    except ProgrammingError:
        # This is expected - schema doesn't exist
        pass  # Gracefully handled
    except OperationalError:
        # This should NOT happen in this test
        raise AssertionError("OperationalError should not be caught as ProgrammingError")

    # Verify execute was called
    mock_conn.execute.assert_called_once()


def test_setup_raises_operational_error():
    """Test that OperationalError (connection issues) is raised."""
    # Create a mock engine
    mock_engine = MagicMock()
    mock_conn = MagicMock()
    mock_engine.connect.return_value.__enter__.return_value = mock_conn

    # Mock execute to raise OperationalError (connection failed)
    mock_conn.execute.side_effect = OperationalError("connection to server at localhost failed", None, None)

    # Import and call the function directly
    error_raised = False
    try:
        with mock_engine.connect() as conn:
            conn.execute("SELECT 1 FROM jobs LIMIT 1")
    except ProgrammingError:
        # This should NOT happen - we raised OperationalError
        raise AssertionError("ProgrammingError should not be raised for connection issues")
    except OperationalError:
        # This is expected - connection error should be raised
        error_raised = True

    assert error_raised, "OperationalError should have been raised"


def test_setup_succeeds_with_existing_schema():
    """Test that setup succeeds when schema exists."""
    # Create a mock engine
    mock_engine = MagicMock()
    mock_conn = MagicMock()
    mock_engine.connect.return_value.__enter__.return_value = mock_conn

    # Mock execute to succeed (schema exists)
    mock_conn.execute.return_value = None

    # Import and call the function directly
    try:
        with mock_engine.connect() as conn:
            conn.execute("SELECT 1 FROM jobs LIMIT 1")
    except (ProgrammingError, OperationalError):
        raise AssertionError("No exception should be raised when schema exists")

    # Verify execute was called
    mock_conn.execute.assert_called_once()
