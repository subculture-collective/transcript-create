"""Validate temporary security exceptions before scanners are allowed to run."""

from __future__ import annotations

import argparse
import ast
import json
import os
import subprocess
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Iterable, Never, cast


@dataclass(frozen=True)
class SecurityException:
    advisory_id: str
    expires_on: date
    forbidden_call: str


# Both historical ML exceptions expired. Scan without suppressions; an
# unavailable compatible wheel is a release blocker, not an implicit renewal.
EXCEPTIONS: tuple[SecurityException, ...] = ()

NPM_SEVERITIES = {"info", "low", "moderate", "high", "critical"}


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


def _security_error(message: str) -> Never:
    raise SystemExit(f"npm security exception gate failed: {message}")


def _validate_router_usage(package_dir: Path) -> None:
    source_root = package_dir / "src"
    if not source_root.is_dir():
        _security_error(f"frontend source directory is missing: {source_root}")
    checker = Path(__file__).resolve().parents[1] / "frontend" / "scripts" / "check-react-router-usage.mjs"
    try:
        result = subprocess.run(["node", str(checker), str(source_root)], check=False, capture_output=True, text=True)
    except OSError as error:
        _security_error(f"could not run React Router AST checker: {error}")
    if result.returncode != 0:
        _security_error(f"React Router AST checker failed ({result.returncode}): {result.stderr.strip()}")
    try:
        output = json.loads(result.stdout)
    except json.JSONDecodeError as error:
        _security_error(f"malformed React Router AST checker output: {error}")
    findings = output.get("findings") if isinstance(output, dict) else None
    if not isinstance(findings, list) or not all(isinstance(finding, str) for finding in findings):
        _security_error("malformed React Router AST checker output")
    if findings:
        _security_error("React Router exception became reachable:\n" + "\n".join(findings))


def validate_npm_audit(*, today: date, package_dir: Path, audit: dict[str, object]) -> None:
    del today
    _validate_router_usage(package_dir)
    vulnerabilities = audit.get("vulnerabilities")
    if not isinstance(vulnerabilities, dict):
        _security_error("audit JSON is missing vulnerabilities")
    vulnerabilities = cast(dict[str, object], vulnerabilities)
    for name, record in vulnerabilities.items():
        if not isinstance(name, str) or not isinstance(record, dict):
            _security_error("malformed vulnerability record")
        record = cast(dict[str, object], record)
        severity = record.get("severity")
        if not isinstance(severity, str) or severity not in NPM_SEVERITIES:
            _security_error(f"malformed or unknown vulnerability severity for {name}")
        if severity in {"high", "critical"}:
            _security_error(f"{severity} vulnerability present: {name}")


def run_npm_audit(*, today: date, package_dir: Path) -> None:
    environment = dict(os.environ)
    environment.update({"NPM_CONFIG_OMIT": "", "NPM_CONFIG_PRODUCTION": "false"})
    try:
        result = subprocess.run(
            ["npm", "audit", "--package-lock-only", "--include=dev", "--audit-level=high", "--json"],
            cwd=package_dir,
            check=False,
            capture_output=True,
            text=True,
            env=environment,
        )
    except OSError as error:
        _security_error(f"could not run npm audit: {error}")
    if result.returncode not in {0, 1}:
        _security_error(f"npm audit command failed ({result.returncode}): {result.stderr.strip()}")
    try:
        audit = json.loads(result.stdout)
    except json.JSONDecodeError as error:
        _security_error(f"malformed npm audit JSON: {error}")
    if not isinstance(audit, dict):
        _security_error("npm audit JSON must be an object")
    validate_npm_audit(today=today, package_dir=package_dir, audit=audit)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pip-audit-args", action="store_true")
    parser.add_argument("--npm-audit", action="store_true")
    parser.add_argument("--package-dir", type=Path)
    args = parser.parse_args()

    today = datetime.now(timezone.utc).date()
    if args.npm_audit:
        if args.pip_audit_args or args.package_dir is None:
            parser.error("--npm-audit requires --package-dir and cannot be combined with --pip-audit-args")
        run_npm_audit(today=today, package_dir=args.package_dir)
        print("npm audit has no high or critical vulnerabilities")
        return
    if args.package_dir is not None:
        parser.error("--package-dir requires --npm-audit")
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
