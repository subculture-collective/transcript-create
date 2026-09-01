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


EXCEPTIONS = (
    SecurityException(
        advisory_id="GHSA-rrmf-rvhw-rf47",
        expires_on=date(2026, 9, 6),
        forbidden_call="torch.jit.script",
    ),
    SecurityException(
        advisory_id="PYSEC-2026-3624",
        expires_on=date(2026, 9, 6),
        forbidden_call="lightning.LightningModule.load_from_checkpoint",
    ),
)

NPM_EXCEPTION_EXPIRY = date(2026, 9, 6)
NPM_BRACE_SOURCES = {
    "1130588": "GHSA-mh99-v99m-4gvg",
    "1130589": "GHSA-mh99-v99m-4gvg",
    "1130736": "GHSA-rgw5-rvv9-x895",
    "1130737": "GHSA-rgw5-rvv9-x895",
}
NPM_ALLOWED_BRACE_NODES = {
    "node_modules/@redocly/openapi-core/node_modules/brace-expansion": "2.1.2",
    "node_modules/@typescript-eslint/typescript-estree/node_modules/brace-expansion": "2.1.2",
    "node_modules/brace-expansion": "1.1.16",
}
NPM_ALLOWED_LEAVES = {
    **NPM_BRACE_SOURCES,
}
NPM_LEAF_AUDIT_NODES = {
    **{source: set(NPM_ALLOWED_BRACE_NODES) for source in NPM_BRACE_SOURCES},
}
NPM_SEVERITIES = {"info", "low", "moderate", "high", "critical"}
NPM_ALLOWED_HIGH_CRITICAL_GRAPH = {
    "brace-expansion": tuple(NPM_BRACE_SOURCES),
}


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


def _load_json(path: Path) -> dict[str, object]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        _security_error(f"cannot parse {path}: {error}")
    if not isinstance(value, dict):
        _security_error(f"{path} must contain a JSON object")
    return cast(dict[str, object], value)


def _validate_lock_nodes(packages: dict[str, object], expected: dict[str, str], *, dev_only: bool) -> None:
    for node_path, version in expected.items():
        entry = packages.get(node_path)
        if not isinstance(entry, dict) or entry.get("version") != version:
            _security_error(f"lockfile node drift: {node_path} must be {version}")
        if dev_only and entry.get("dev") is not True:
            _security_error(f"lockfile node must be dev-only: {node_path}")


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


def _via_graph(record: dict[str, object], name: str) -> tuple[str, ...]:
    via = record.get("via")
    if not isinstance(via, list) or not via:
        _security_error(f"vulnerability {name} has no resolvable via chain")
    graph: list[str] = []
    for item in via:
        if isinstance(item, str):
            graph.append(item)
        elif isinstance(item, dict) and isinstance(item.get("source"), int):
            graph.append(str(item["source"]))
        else:
            _security_error(f"malformed via entry for {name}")
    return tuple(graph)


def _leaf_sources(name: str, vulnerabilities: dict[str, object], visiting: set[str]) -> set[str]:
    if name in visiting:
        _security_error(f"cyclic audit via reference at {name}")
    record = vulnerabilities.get(name)
    if not isinstance(record, dict):
        _security_error(f"unresolved audit via reference: {name}")
    via = record.get("via")
    if not isinstance(via, list) or not via:
        _security_error(f"vulnerability {name} has no resolvable via chain")
    leaves: set[str] = set()
    for item in via:
        if isinstance(item, str):
            leaves.update(_leaf_sources(item, vulnerabilities, visiting | {name}))
        elif isinstance(item, dict):
            source = item.get("source")
            url = item.get("url")
            if not isinstance(source, int) or not isinstance(url, str):
                _security_error(f"malformed advisory leaf for {name}")
            source_id = str(source)
            expected_ghsa = NPM_ALLOWED_LEAVES.get(source_id)
            if expected_ghsa is None or expected_ghsa not in url:
                _security_error(f"unexpected advisory leaf {source_id} for {name}")
            leaves.add(source_id)
        else:
            _security_error(f"malformed via entry for {name}")
    return leaves


def validate_npm_audit(*, today: date, package_dir: Path, audit: dict[str, object]) -> None:
    if today >= NPM_EXCEPTION_EXPIRY:
        _security_error(f"exceptions expired {NPM_EXCEPTION_EXPIRY.isoformat()} UTC")
    vulnerabilities = audit.get("vulnerabilities")
    if not isinstance(vulnerabilities, dict):
        _security_error("audit JSON is missing vulnerabilities")
    vulnerabilities = cast(dict[str, object], vulnerabilities)
    lock = _load_json(package_dir / "package-lock.json")
    packages = lock.get("packages")
    if not isinstance(packages, dict):
        _security_error("lockfile is missing packages")
    packages = cast(dict[str, object], packages)
    _validate_lock_nodes(packages, NPM_ALLOWED_BRACE_NODES, dev_only=True)

    high_critical: set[str] = set()
    for name, record in vulnerabilities.items():
        if not isinstance(name, str) or not isinstance(record, dict):
            _security_error("malformed vulnerability record")
        record = cast(dict[str, object], record)
        severity = record.get("severity")
        if not isinstance(severity, str) or severity not in NPM_SEVERITIES:
            _security_error(f"malformed or unknown vulnerability severity for {name}")
        if severity == "critical":
            _security_error(f"critical vulnerability present: {name}")
        if severity == "high":
            high_critical.add(name)
    declared_sources = {
        str(item["source"])
        for record in vulnerabilities.values()
        if isinstance(record, dict) and isinstance(record.get("via"), list)
        for item in record["via"]
        if isinstance(item, dict) and isinstance(item.get("source"), int)
    }
    if not set(NPM_ALLOWED_LEAVES).issubset(declared_sources):
        _security_error(f"missing expected advisory sources: {sorted(set(NPM_ALLOWED_LEAVES) - declared_sources)}")
    validated_sources: set[str] = set()
    for name, record in vulnerabilities.items():
        if not isinstance(name, str) or not isinstance(record, dict):
            _security_error("malformed vulnerability record")
        record = cast(dict[str, object], record)
        severity = record.get("severity")
        if severity not in {"high", "critical"}:
            continue
        leaves = _leaf_sources(name, vulnerabilities, set())
        if not leaves:
            _security_error(f"vulnerability {name} has no advisory leaves")
        for source in leaves:
            if source in validated_sources:
                continue
            leaf_record = vulnerabilities.get("brace-expansion")
            if not isinstance(leaf_record, dict):
                _security_error(f"missing direct audit record for advisory {source}")
            nodes = leaf_record.get("nodes")
            if not isinstance(nodes, list) or not all(isinstance(node, str) for node in nodes):
                _security_error(f"vulnerability audit nodes are malformed for advisory {source}")
            if set(nodes) != NPM_LEAF_AUDIT_NODES[source]:
                _security_error(f"audit path drift for advisory {source}: {nodes}")
            validated_sources.add(source)
    if validated_sources != set(NPM_ALLOWED_LEAVES):
        _security_error(f"missing expected advisory sources: {sorted(set(NPM_ALLOWED_LEAVES) - validated_sources)}")
    if high_critical != set(NPM_ALLOWED_HIGH_CRITICAL_GRAPH):
        _security_error(f"high/critical audit record graph drift: {sorted(high_critical)}")
    for name, expected_via in NPM_ALLOWED_HIGH_CRITICAL_GRAPH.items():
        record = vulnerabilities[name]
        assert isinstance(record, dict)
        if _via_graph(cast(dict[str, object], record), name) != expected_via:
            _security_error(f"high/critical audit graph edge drift for {name}")


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
        print("npm security exceptions are unexpired, unreachable, and lockfile-pinned")
        return
    if args.package_dir is not None:
        parser.error("--package-dir requires --npm-audit")
    validate(today=today, roots=(Path("app"), Path("worker")))
    if args.pip_audit_args:
        print(" ".join(f"--ignore-vuln {item.advisory_id}" for item in EXCEPTIONS))
    else:
        print("security exceptions are unexpired and unreachable")


if __name__ == "__main__":
    main()
