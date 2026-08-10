"""Deployment contract tests for browser and API content security policies."""

import re
from pathlib import Path

from app.middleware import API_CONTENT_SECURITY_POLICY

ROOT = Path(__file__).resolve().parents[1]
LIVE_CSP_FILES = (
    "app/middleware.py",
    "frontend/nginx.conf",
    "charts/transcript-create/values-prod.yaml",
    "k8s/ingress.yaml",
)


def _parse_directives(policy: str) -> dict[str, set[str]]:
    directives: dict[str, set[str]] = {}
    for raw_directive in policy.strip().rstrip(";").split(";"):
        name, *sources = raw_directive.strip().split()
        directives[name] = set(sources)
    return directives


def _nginx_frontend_policy() -> str:
    config = (ROOT / "frontend" / "nginx.conf").read_text()
    match = re.search(
        r'add_header\s+Content-Security-Policy\s+"([^"]+)"\s+always;',
        config,
    )
    assert match is not None, "frontend nginx must set CSP on every response"
    return match.group(1)


def _ingress_api_policy(relative_path: str) -> str:
    config = (ROOT / relative_path).read_text()
    match = re.search(r'Content-Security-Policy:\s*([^"\n]+)', config)
    assert match is not None, f"{relative_path} must set the API CSP"
    return match.group(1).strip().rstrip(";")


def test_frontend_nginx_serves_a_strict_application_csp():
    policy = _nginx_frontend_policy()
    directives = _parse_directives(policy)

    assert "unsafe-inline" not in policy
    assert "unsafe-eval" not in policy
    assert all("*" not in source for sources in directives.values() for source in sources)
    assert directives == {
        "default-src": {"'self'"},
        "base-uri": {"'self'"},
        "connect-src": {"'self'"},
        "font-src": {"'self'", "data:", "https://fonts.gstatic.com"},
        "form-action": {"'self'"},
        "frame-ancestors": {"'none'"},
        "frame-src": {"https://www.youtube.com"},
        # OAuth and user-configured avatars are absolute HTTPS URLs. Keep
        # non-HTTPS images blocked without restricting profiles to fixed hosts.
        "img-src": {"'self'", "data:", "https:"},
        "object-src": {"'none'"},
        "script-src": {"'self'", "https://www.youtube.com"},
        "style-src": {"'self'", "https://fonts.googleapis.com"},
    }


def test_api_ingress_policies_match_the_runtime_api_policy():
    for relative_path in (
        "charts/transcript-create/values-prod.yaml",
        "k8s/ingress.yaml",
    ):
        assert _ingress_api_policy(relative_path) == API_CONTENT_SECURITY_POLICY


def test_live_csp_definitions_never_enable_unsafe_script_or_style_execution():
    for relative_path in LIVE_CSP_FILES:
        config = (ROOT / relative_path).read_text()
        assert "unsafe-inline" not in config, relative_path
        assert "unsafe-eval" not in config, relative_path


def test_frontend_react_sources_do_not_use_inline_style_properties():
    offenders = [
        str(path.relative_to(ROOT))
        for path in (ROOT / "frontend" / "src").rglob("*.tsx")
        if re.search(r"\bstyle\s*=", path.read_text())
    ]
    assert offenders == []
