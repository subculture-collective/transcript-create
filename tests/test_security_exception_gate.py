import subprocess
from datetime import date
from pathlib import Path

import pytest

from scripts import check_security_exceptions
from scripts.check_security_exceptions import SecurityException, reachable_calls, validate


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
    gate = script.split("# Preserve the validator")[1].split("echo 'Checking the committed OpenAPI contract...'")[0]
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
