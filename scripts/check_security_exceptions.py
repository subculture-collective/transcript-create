"""Validate temporary security exceptions before scanners are allowed to run."""

from __future__ import annotations

import argparse
import ast
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Iterable


@dataclass(frozen=True)
class SecurityException:
    advisory_id: str
    expires_on: date
    forbidden_call: str


# Both historical ML exceptions expired. Scan without suppressions; an
# unavailable compatible wheel is a release blocker, not an implicit renewal.
EXCEPTIONS: tuple[SecurityException, ...] = ()


def _import_aliases(tree: ast.AST) -> dict[str, str]:
    aliases: dict[str, str] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for imported in node.names:
                bound_name = imported.asname or imported.name.split(".", 1)[0]
                aliases[bound_name] = imported.name if imported.asname else bound_name
        elif isinstance(node, ast.ImportFrom) and node.module:
            for imported in node.names:
                if imported.name == "*":
                    continue
                bound_name = imported.asname or imported.name
                aliases[bound_name] = f"{node.module}.{imported.name}"
    return aliases


def _call_name(node: ast.expr, aliases: dict[str, str]) -> str | None:
    parts: list[str] = []
    current: ast.expr = node
    while isinstance(current, ast.Attribute):
        parts.append(current.attr)
        current = current.value
    if not isinstance(current, ast.Name):
        return None
    root = aliases.get(current.id, current.id)
    return ".".join([root, *reversed(parts)])


def reachable_calls(paths: Iterable[Path]) -> list[str]:
    forbidden = {exception.forbidden_call for exception in EXCEPTIONS}
    findings: list[str] = []
    for root in paths:
        for path in root.rglob("*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            aliases = _import_aliases(tree)
            for node in ast.walk(tree):
                if isinstance(node, ast.Call):
                    name = _call_name(node.func, aliases)
                    if name in forbidden:
                        findings.append(f"{path}:{node.lineno}: {name}")
    return findings


def validate(*, today: date, roots: Iterable[Path]) -> None:
    expired = [item for item in EXCEPTIONS if today >= item.expires_on]
    if expired:
        details = ", ".join(f"{item.advisory_id} expired {item.expires_on.isoformat()}" for item in expired)
        raise SystemExit(f"security exception expired: {details}")

    findings = reachable_calls(roots)
    if findings:
        raise SystemExit("temporary security exception became reachable:\n" + "\n".join(findings))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pip-audit-args", action="store_true")
    args = parser.parse_args()

    today = datetime.now(timezone.utc).date()
    validate(today=today, roots=(Path("app"), Path("worker")))
    if args.pip_audit_args:
        print(" ".join(f"--ignore-vuln {item.advisory_id}" for item in EXCEPTIONS))
    else:
        print(
            "security exception policy passed (no active exceptions)"
            if not EXCEPTIONS
            else "security exceptions are unexpired and unreachable"
        )


if __name__ == "__main__":
    main()
