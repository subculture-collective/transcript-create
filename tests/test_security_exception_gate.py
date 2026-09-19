import json
import subprocess
from datetime import date
from pathlib import Path

import pytest

from scripts import check_security_exceptions
from scripts.check_security_exceptions import (
    SecurityException,
    reachable_calls,
    run_npm_audit,
    validate,
    validate_npm_audit,
)


@pytest.fixture
def temporary_exception(monkeypatch):
    monkeypatch.setattr(
        check_security_exceptions,
        "EXCEPTIONS",
        (SecurityException("test-advisory", date(2026, 9, 13), "torch.jit.script"),),
    )


def test_no_expired_ml_suppressions_remain():
    assert check_security_exceptions.EXCEPTIONS == ()


def test_local_verify_stops_when_exception_validation_fails(tmp_path: Path) -> None:
    script = (Path(__file__).parents[1] / "scripts" / "verify.sh").read_text()
    gate = script.split("# Preserve the validator")[1].split("echo 'Running frontend verification...'")[0]
    fake_python = tmp_path / "python"
    fake_python.write_text(
        '#!/bin/sh\nif [ "$1" = scripts/check_security_exceptions.py ]; then exit 42; fi\necho scanner-ran\n'
    )
    fake_python.chmod(0o755)
    result = subprocess.run(
        [
            "bash",
            "-c",
            'set -euo pipefail\nPYTHON_BIN="$1"\n# Preserve the validator' + gate,
            "verify-gate",
            str(fake_python),
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 42
    assert "scanner-ran" not in result.stdout


def test_reachability_finds_qualified_and_aliased_calls(tmp_path: Path, temporary_exception) -> None:
    (tmp_path / "qualified.py").write_text("import torch\ntorch.jit.script(lambda: None)\n")
    (tmp_path / "aliased.py").write_text(
        "from torch.jit import script as compile_script\ncompile_script(lambda: None)\n"
    )

    findings = reachable_calls((tmp_path,))

    assert len(findings) == 2
    assert all("torch.jit.script" in finding for finding in findings)


def test_exception_fails_on_utc_expiry(tmp_path: Path, temporary_exception) -> None:
    with pytest.raises(SystemExit, match="expired 2026-09-13"):
        validate(today=date(2026, 9, 13), roots=(tmp_path,))


def test_exception_is_valid_before_expiry_when_unreachable(tmp_path: Path, temporary_exception) -> None:
    (tmp_path / "safe.py").write_text("import torch\nprint(torch.__version__)\n")

    validate(today=date(2026, 9, 12), roots=(tmp_path,))


def _npm_package(tmp_path: Path) -> Path:
    package_dir = tmp_path / "frontend"
    (package_dir / "src").mkdir(parents=True)
    (package_dir / "src" / "main.tsx").write_text(
        'import { Link } from "react-router-dom";\nvoid Link;\n', encoding="utf-8"
    )
    (package_dir / "package.json").write_text('{"dependencies":{"react-router-dom":"7.18.2"}}', encoding="utf-8")
    packages = {}
    (package_dir / "package-lock.json").write_text(json.dumps({"packages": packages}), encoding="utf-8")
    return package_dir


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


def test_npm_audit_allows_no_high_or_critical_vulnerabilities(tmp_path: Path) -> None:
    audit = {"vulnerabilities": {"low-risk": {"severity": "low"}}}
    validate_npm_audit(today=date(2026, 8, 7), package_dir=_npm_package(tmp_path), audit=audit)


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


def test_npm_exception_rejects_unknown_severity(tmp_path: Path) -> None:
    audit = {"vulnerabilities": {"unknown": {"severity": "urgent"}}}
    with pytest.raises(SystemExit, match="unknown vulnerability severity"):
        validate_npm_audit(today=date(2026, 8, 7), package_dir=_npm_package(tmp_path), audit=audit)


@pytest.mark.parametrize("severity", ["high", "critical"])
def test_npm_audit_rejects_high_and_critical_vulnerabilities(tmp_path: Path, severity: str) -> None:
    audit = {"vulnerabilities": {"unsafe-package": {"severity": severity}}}
    with pytest.raises(SystemExit, match=f"{severity} vulnerability present: unsafe-package"):
        validate_npm_audit(today=date(2026, 8, 7), package_dir=_npm_package(tmp_path), audit=audit)


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
