import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts import check_lightning_patch as gate


@pytest.fixture
def package(tmp_path, monkeypatch):
    source = tmp_path / "saving.py"
    source.write_text("patched source")
    monkeypatch.setattr(
        gate, "SOURCES", {"lightning": ("fake_lightning", hashlib.sha256(source.read_bytes()).hexdigest())}
    )
    package = SimpleNamespace(version="2.6.6", locate_file=lambda _: source)
    monkeypatch.setattr(gate, "distribution", lambda _: package)
    return package, source


def test_patch_gate_rejects_version_and_source_drift(package):
    distribution, source = package
    distribution.version = "2.6.5"
    with pytest.raises(SystemExit, match="requires"):
        gate.main()
    distribution.version = "2.6.6"
    source.write_text("different source")
    with pytest.raises(SystemExit, match="hash differs"):
        gate.main()


def test_patch_gate_requires_rejection_not_just_matching_metadata(package, monkeypatch):
    module = SimpleNamespace(LightningModule=object, _load_state=lambda *args: None)
    monkeypatch.setattr(gate.importlib, "import_module", lambda _: module)
    with pytest.raises(SystemExit, match="not rejected"):
        gate.main()


def test_patch_gate_accepts_patched_behavior(package, monkeypatch):
    def reject(*args):
        raise ValueError("blocked to prevent arbitrary code execution")

    module = SimpleNamespace(LightningModule=object, _load_state=reject)
    monkeypatch.setattr(gate.importlib, "import_module", lambda _: module)
    gate.main()


def test_vex_is_scoped_to_one_fixed_package_version_and_advisory():
    path = Path(__file__).parents[1] / "security/lightning-2.6.6.vex.json"
    statements = json.loads(path.read_text())["statements"]
    assert len(statements) == 1
    assert statements[0]["products"] == [{"@id": "pkg:pypi/lightning@2.6.6"}]
    assert statements[0]["vulnerability"] == {"name": "CVE-2026-58659"}
    assert statements[0]["status"] == "fixed"
