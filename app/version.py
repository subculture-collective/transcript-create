"""Version information utility for the application."""

import os


def get_version() -> str:
    """
    Read version from pyproject.toml.

    Returns:
        Version string or "unknown" if unable to read.
    """
    try:
        import tomllib
    except ModuleNotFoundError:
        return "unknown"

    pyproject_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "pyproject.toml")
    try:
        with open(pyproject_path, "rb") as f:
            pyproject_data = tomllib.load(f)
            return pyproject_data.get("project", {}).get("version", "unknown")
    except (FileNotFoundError, OSError, KeyError):
        return "unknown"
    except Exception:
        # Catch tomllib.TOMLDecodeError (Python 3.11+) without importing tomllib globally
        return "unknown"


def get_git_commit() -> str:
    """
    Get git commit hash from environment.

    Returns:
        Git commit hash or "unknown" if not set.
    """
    return os.getenv("GIT_COMMIT", "unknown")


def get_build_date() -> str:
    """
    Get build date from environment.

    Returns:
        Build date or "unknown" if not set.
    """
    return os.getenv("BUILD_DATE", "unknown")
