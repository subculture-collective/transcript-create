"""Test utilities and helper functions."""


def verify_oauth_token(provider: str, token: str) -> dict:  # pragma: no cover
    """Verify an OAuth access token and return user info.

    This is a test utility shim to support tests that monkeypatch this function.
    In production, the implementation uses Authlib's authorize_access_token and
    provider APIs directly within the request flow, so this function is not called.
    Tests may patch it to inject deterministic user info.

    This function should be monkeypatched in tests that need to simulate OAuth
    token verification without making actual API calls to OAuth providers.
    """
    raise NotImplementedError("verify_oauth_token is a test-only shim and should be monkeypatched in tests")
