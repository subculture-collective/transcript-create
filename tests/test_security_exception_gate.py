import json
import subprocess
from datetime import date
from pathlib import Path

import pytest

from scripts.check_security_exceptions import (
    NPM_ALLOWED_HIGH_CRITICAL_GRAPH,
    NPM_ALLOWED_LEAVES,
    reachable_calls,
    run_npm_audit,
    validate,
    validate_npm_audit,
)


def test_reachability_finds_qualified_and_aliased_calls(tmp_path: Path) -> None:
    (tmp_path / "qualified.py").write_text("import torch\ntorch.jit.script(lambda: None)\n")
    (tmp_path / "aliased.py").write_text(
        "from torch.jit import script as compile_script\ncompile_script(lambda: None)\n"
    )

    findings = reachable_calls((tmp_path,))

    assert len(findings) == 2
    assert all("torch.jit.script" in finding for finding in findings)


def test_exception_fails_on_utc_expiry(tmp_path: Path) -> None:
    with pytest.raises(SystemExit, match="expired 2026-09-06"):
        validate(today=date(2026, 9, 6), roots=(tmp_path,))


def test_exception_is_valid_before_expiry_when_unreachable(tmp_path: Path) -> None:
    (tmp_path / "safe.py").write_text("import torch\nprint(torch.__version__)\n")

    validate(today=date(2026, 9, 5), roots=(tmp_path,))


def _npm_package(tmp_path: Path) -> Path:
    package_dir = tmp_path / "frontend"
    (package_dir / "src").mkdir(parents=True)
    (package_dir / "src" / "main.tsx").write_text(
        'import { Link } from "react-router-dom";\nvoid Link;\n', encoding="utf-8"
    )
    (package_dir / "package.json").write_text('{"dependencies":{"react-router-dom":"7.18.2"}}', encoding="utf-8")
    packages = {
        "node_modules/react-router": {"version": "7.18.2"},
        "node_modules/react-router-dom": {"version": "7.18.2"},
        "node_modules/brace-expansion": {"version": "1.1.16", "dev": True},
        "node_modules/@redocly/openapi-core/node_modules/brace-expansion": {
            "version": "2.1.2",
            "dev": True,
        },
        "node_modules/@typescript-eslint/typescript-estree/node_modules/brace-expansion": {
            "version": "2.1.2",
            "dev": True,
        },
    }
    (package_dir / "package-lock.json").write_text(json.dumps({"packages": packages}), encoding="utf-8")
    return package_dir


def _advisory(source: int, ghsa: str) -> dict[str, object]:
    return {"source": source, "url": f"https://github.com/advisories/{ghsa}"}


def _allowed_audit() -> dict[str, object]:
    vulnerabilities: dict[str, object] = {}
    for name, via in NPM_ALLOWED_HIGH_CRITICAL_GRAPH.items():
        resolved_via: list[object] = list(via)
        if name == "brace-expansion":
            resolved_via = [_advisory(int(source), ghsa) for source, ghsa in NPM_ALLOWED_LEAVES.items()]
        vulnerabilities[name] = {"severity": "high", "via": resolved_via, "nodes": [f"node_modules/{name}"]}
    vulnerabilities["brace-expansion"] = {
        "severity": "high",
        "via": [_advisory(int(source), ghsa) for source, ghsa in NPM_ALLOWED_LEAVES.items()],
        "nodes": [
            "node_modules/brace-expansion",
            "node_modules/@redocly/openapi-core/node_modules/brace-expansion",
            "node_modules/@typescript-eslint/typescript-estree/node_modules/brace-expansion",
        ],
    }
    return {"vulnerabilities": vulnerabilities}


def _router_findings(tmp_path: Path, source: str, filename: str = "source.ts") -> list[str]:
    source_dir = tmp_path / "source"
    source_dir.mkdir()
    (source_dir / filename).write_text(source, encoding="utf-8")
    checker = Path(__file__).parents[1] / "frontend" / "scripts" / "check-react-router-usage.mjs"
    result = subprocess.run(["node", str(checker), str(source_dir)], check=True, capture_output=True, text=True)
    return json.loads(result.stdout)["findings"]


@pytest.mark.parametrize(
    "source",
    [
        'import { Link } from "react-router-dom";\n',
        'import { Link } from "react-router-domestic";\n',
        'import("./lazy-route");\n',
        'require("unrelated-package");\n',
    ],
)
def test_router_checker_allows_safe_usage(tmp_path: Path, source: str) -> None:
    assert _router_findings(tmp_path, source) == []


@pytest.mark.parametrize(
    "source, filename",
    [
        ('import "react-router-dom/server";\n', "subpath.ts"),
        ('import("react-router-dom", { with: { type: "json" } });\n', "dynamic-options.ts"),
        ('import(`react-router-dom/server`, { with: { type: "json" } });\n', "template-options.ts"),
        ("import(moduleName);\n", "computed-dynamic.ts"),
        ('require("react-router-dom/server");\n', "router-require.cjs"),
        ("require(moduleName);\n", "computed-require.cjs"),
        ('import router = require("react-router-dom");\n', "import-equals.ts"),
        ('import router = require("react-router-dom/server");\n', "import-equals-subpath.ts"),
        ('import { Link from "react-router-dom";\n', "malformed.ts"),
    ],
)
def test_router_checker_rejects_unsafe_usage(tmp_path: Path, source: str, filename: str) -> None:
    assert _router_findings(tmp_path, source, filename)


def test_npm_exception_allows_exact_recursive_audit_graph(tmp_path: Path) -> None:
    validate_npm_audit(today=date(2026, 8, 7), package_dir=_npm_package(tmp_path), audit=_allowed_audit())


def test_npm_exception_rejects_unexpected_advisory(tmp_path: Path) -> None:
    audit = _allowed_audit()
    audit["vulnerabilities"]["other"] = {  # type: ignore[index]
        "severity": "high",
        "via": [_advisory(999, "GHSA-unexpected")],
        "nodes": ["node_modules/other"],
    }
    with pytest.raises(SystemExit, match="unexpected advisory leaf 999"):
        validate_npm_audit(today=date(2026, 8, 7), package_dir=_npm_package(tmp_path), audit=audit)


def test_npm_exception_fails_on_expiry(tmp_path: Path) -> None:
    with pytest.raises(SystemExit, match="expired 2026-09-06 UTC"):
        validate_npm_audit(today=date(2026, 9, 6), package_dir=_npm_package(tmp_path), audit=_allowed_audit())


def test_npm_exception_rejects_malformed_audit(tmp_path: Path) -> None:
    with pytest.raises(SystemExit, match="missing vulnerabilities"):
        validate_npm_audit(today=date(2026, 8, 7), package_dir=_npm_package(tmp_path), audit={})


def test_npm_exception_rejects_malformed_audit_json(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "scripts.check_security_exceptions.subprocess.run",
        lambda *args, **kwargs: subprocess.CompletedProcess(args, 1, "not json", ""),
    )
    with pytest.raises(SystemExit, match="malformed npm audit JSON"):
        run_npm_audit(today=date(2026, 8, 7), package_dir=_npm_package(tmp_path))


@pytest.mark.parametrize("via, message", [(["missing"], "unresolved"), (["cycle"], "cyclic")])
def test_npm_exception_rejects_unresolved_and_cyclic_via(tmp_path: Path, via: list[str], message: str) -> None:
    audit = _allowed_audit()
    audit["vulnerabilities"]["cycle"] = {"severity": "high", "via": via, "nodes": ["node_modules/cycle"]}  # type: ignore[index]
    with pytest.raises(SystemExit, match=message):
        validate_npm_audit(today=date(2026, 8, 7), package_dir=_npm_package(tmp_path), audit=audit)


def test_npm_exception_rejects_unknown_severity(tmp_path: Path) -> None:
    audit = _allowed_audit()
    audit["vulnerabilities"]["brace-expansion"]["severity"] = "urgent"  # type: ignore[index]
    with pytest.raises(SystemExit, match="unknown vulnerability severity"):
        validate_npm_audit(today=date(2026, 8, 7), package_dir=_npm_package(tmp_path), audit=audit)


def test_npm_exception_rejects_critical_vulnerability(tmp_path: Path) -> None:
    audit = _allowed_audit()
    audit["vulnerabilities"]["brace-expansion"]["severity"] = "critical"  # type: ignore[index]
    with pytest.raises(SystemExit, match="critical vulnerability present: brace-expansion"):
        validate_npm_audit(today=date(2026, 8, 7), package_dir=_npm_package(tmp_path), audit=audit)


def test_npm_exception_rejects_extra_cascade_to_allowed_source(tmp_path: Path) -> None:
    audit = _allowed_audit()
    audit["vulnerabilities"]["unexpected-cascade"] = {"severity": "high", "via": ["brace-expansion"], "nodes": []}  # type: ignore[index]
    with pytest.raises(SystemExit, match="graph drift"):
        validate_npm_audit(today=date(2026, 8, 7), package_dir=_npm_package(tmp_path), audit=audit)


def test_npm_exception_rejects_audit_missing_expected_source(tmp_path: Path) -> None:
    audit = _allowed_audit()
    audit["vulnerabilities"].pop("brace-expansion")  # type: ignore[index]
    with pytest.raises(SystemExit, match="missing expected advisory sources"):
        validate_npm_audit(today=date(2026, 8, 7), package_dir=_npm_package(tmp_path), audit=audit)


def test_npm_exception_rejects_empty_audit_missing_expected_sources(tmp_path: Path) -> None:
    with pytest.raises(SystemExit, match="missing expected advisory sources"):
        validate_npm_audit(today=date(2026, 8, 7), package_dir=_npm_package(tmp_path), audit={"vulnerabilities": {}})


def test_npm_audit_command_includes_dev_and_rejects_fatal_return(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    captured: dict[str, object] = {}

    def fake_run(*args: object, **kwargs: object) -> subprocess.CompletedProcess[str]:
        captured["args"] = args
        captured["kwargs"] = kwargs
        return subprocess.CompletedProcess([], 2, "", "fatal")

    monkeypatch.setattr("scripts.check_security_exceptions.subprocess.run", fake_run)
    with pytest.raises(SystemExit, match=r"command failed \(2\)"):
        run_npm_audit(today=date(2026, 8, 7), package_dir=_npm_package(tmp_path))
    assert captured["args"] == (
        ["npm", "audit", "--package-lock-only", "--include=dev", "--audit-level=high", "--json"],
    )
    environment = captured["kwargs"]["env"]  # type: ignore[index]
    assert environment["NPM_CONFIG_OMIT"] == ""  # type: ignore[index]
    assert environment["NPM_CONFIG_PRODUCTION"] == "false"  # type: ignore[index]


@pytest.mark.parametrize("change", ["non-dev", "path-drift"])
def test_npm_exception_rejects_brace_node_dev_or_path_drift(tmp_path: Path, change: str) -> None:
    package_dir = _npm_package(tmp_path)

    lock = json.loads((package_dir / "package-lock.json").read_text(encoding="utf-8"))
    if change == "non-dev":
        lock["packages"]["node_modules/brace-expansion"]["dev"] = False
    else:
        audit = _allowed_audit()
        audit["vulnerabilities"]["brace-expansion"]["nodes"] = ["node_modules/elsewhere/brace-expansion"]  # type: ignore[index]
    (package_dir / "package-lock.json").write_text(json.dumps(lock), encoding="utf-8")
    with pytest.raises(SystemExit, match="dev-only|path drift"):
        validate_npm_audit(
            today=date(2026, 8, 7), package_dir=package_dir, audit=locals().get("audit", _allowed_audit())
        )
