"""Deployment contract tests for the API content security policy.

Core no longer ships a browser application. Each archive frontend owns its own
document CSP; core only keeps the API policy consistent across deployments.
"""

import re
from pathlib import Path

from app.middleware import API_CONTENT_SECURITY_POLICY

ROOT = Path(__file__).resolve().parents[1]
LIVE_CSP_FILES = (
    "app/middleware.py",
    "charts/transcript-create/values-prod.yaml",
    "k8s/ingress.yaml",
)


def _ingress_api_policy(relative_path: str) -> str:
    config = (ROOT / relative_path).read_text()
    match = re.search(r'Content-Security-Policy:\s*([^"\n]+)', config)
    assert match is not None, f"{relative_path} must set the API CSP"
    return match.group(1).strip().rstrip(";")


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
