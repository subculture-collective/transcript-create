"""Validate canonical documentation, local links, and retired product surfaces."""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CANONICAL = (
    "README.md",
    "docs/STATUS.md",
    "docs/access-matrix.md",
    "docs/api-reference.md",
    "docs/ACCESSIBILITY.md",
    "docs/DESIGN_SYSTEM.md",
    "docs/MIGRATIONS.md",
    "docs/development/architecture.md",
    "docs/development/testing.md",
    "docs/deployment/README.md",
    "docs/deployment/private-beta.md",
    "docs/operations/production-readiness.md",
    "docs/review-traceability.md",
    "docs/user-testing/private-beta.md",
)
LINK = re.compile(r"\[[^]]+\]\(([^)]+)\)")


def validate_links(path: Path, errors: list[str]) -> None:
    for target in LINK.findall(path.read_text(encoding="utf-8")):
        if target.startswith(("http://", "https://", "#")):
            continue
        local = target.split("#", 1)[0]
        if local and not (path.parent / local).resolve().exists():
            errors.append(f"{path.relative_to(ROOT)}: missing link target {local}")


def main() -> int:
    errors: list[str] = []
    for relative in CANONICAL:
        path = ROOT / relative
        if not path.exists():
            errors.append(f"missing canonical document: {relative}")
            continue
        if relative != "README.md" and "**Status:**" not in path.read_text(encoding="utf-8"):
            errors.append(f"{relative}: missing status metadata")
        validate_links(path, errors)

    retired_assets = (
        "frontend/public/offline.html",
        "frontend/public/manifest.json",
    )
    for relative in retired_assets:
        if (ROOT / relative).exists():
            errors.append(f"retired PWA asset exists: {relative}")

    retirement_worker = ROOT / "frontend/public/sw.js"
    if retirement_worker.exists():
        worker_source = retirement_worker.read_text(encoding="utf-8")
        required_retirement_markers = (
            "caches.keys()",
            "caches.delete(key)",
            "self.registration.unregister()",
            "self.clients.matchAll",
            "client.navigate(client.url)",
        )
        if any(marker not in worker_source for marker in required_retirement_markers):
            errors.append("frontend/public/sw.js is not the approved retirement worker")
        if "addEventListener('fetch'" in worker_source or "cache.put(" in worker_source:
            errors.append("frontend/public/sw.js must not cache or intercept application requests")

    retired_sources = (
        "requirements.txt",
        "constraints.txt",
        ".env.example",
        "k8s/api-deployment.yaml",
        "k8s/secrets.yaml",
    )
    for relative in retired_sources:
        text = (ROOT / relative).read_text(encoding="utf-8").lower()
        if "stripe" in text:
            errors.append(f"retired Stripe configuration remains in {relative}")

    frontend_runtime = "\n".join(
        (ROOT / relative).read_text(encoding="utf-8") for relative in ("frontend/src/main.tsx", "frontend/index.html")
    )
    for marker in ("serviceWorker", "manifest.json", "offline.html", "sw.js"):
        if marker in frontend_runtime:
            errors.append(f"retired PWA runtime marker remains: {marker}")

    route_source = (ROOT / "frontend/src/main.tsx").read_text(encoding="utf-8")
    for route in (
        "search",
        "explore",
        "episodes",
        "timeline",
        "topics/:query",
        "v/:videoId",
        "login",
        "saved",
        "favorites",
        "admin",
    ):
        if f"path: '{route}'" not in route_source:
            errors.append(f"documented frontend route missing from router: {route}")

    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    if "make verify" not in readme or "Python 3.11" not in readme or "Node.js 20" not in readme:
        errors.append("README is missing the canonical runtime or verification command")

    if errors:
        print("Documentation validation failed:")
        for error in errors:
            print(f"- {error}")
        return 1
    print("Documentation and retirement contracts passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
