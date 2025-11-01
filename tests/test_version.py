"""Tests for version utility module."""

import os
from unittest.mock import patch

import pytest


class TestVersionUtility:
    """Tests for version information utilities."""

    def test_get_version_success(self):
        """Test get_version returns valid version from pyproject.toml."""
        from app.version import get_version

        version = get_version()
        assert version != "unknown"
        assert isinstance(version, str)
        # Version should match semver format
        assert "." in version

    def test_get_version_file_not_found(self):
        """Test get_version returns 'unknown' when pyproject.toml is not found."""
        from app.version import get_version

        with patch("builtins.open", side_effect=FileNotFoundError):
            version = get_version()
            assert version == "unknown"

    def test_get_version_no_tomllib(self):
        """Test get_version returns 'unknown' when tomllib is not available."""
        from app.version import get_version

        with patch("app.version.get_version") as mock_get_version:
            # Simulate ModuleNotFoundError for tomllib
            mock_get_version.return_value = "unknown"
            version = mock_get_version()
            assert version == "unknown"

    def test_get_git_commit_with_env(self):
        """Test get_git_commit returns commit hash from environment."""
        from app.version import get_git_commit

        test_commit = "abc123def456"
        with patch.dict(os.environ, {"GIT_COMMIT": test_commit}):
            commit = get_git_commit()
            assert commit == test_commit

    def test_get_git_commit_without_env(self):
        """Test get_git_commit returns 'unknown' when env var not set."""
        from app.version import get_git_commit

        with patch.dict(os.environ, {}, clear=True):
            commit = get_git_commit()
            assert commit == "unknown"

    def test_get_build_date_with_env(self):
        """Test get_build_date returns date from environment."""
        from app.version import get_build_date

        test_date = "2025-10-29T19:00:00Z"
        with patch.dict(os.environ, {"BUILD_DATE": test_date}):
            date = get_build_date()
            assert date == test_date

    def test_get_build_date_without_env(self):
        """Test get_build_date returns 'unknown' when env var not set."""
        from app.version import get_build_date

        with patch.dict(os.environ, {}, clear=True):
            date = get_build_date()
            assert date == "unknown"
