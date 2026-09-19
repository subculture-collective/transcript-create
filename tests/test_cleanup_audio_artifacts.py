"""Exercise the operator cleanup utility only against disposable fixtures."""

import os
import subprocess
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "cleanup_audio_artifacts.sh"


def run(*args, cwd, env=None):
    return subprocess.run(["bash", str(SCRIPT), *args], cwd=cwd, env=env, capture_output=True, text=True)


def test_dry_run_and_exact_deletion_with_unusual_paths(tmp_path):
    target = tmp_path / "-job directory"
    nested = target / "line\nbreak"
    nested.mkdir(parents=True)
    matching = [target / "raw.m4a", nested / "chunk_0123.wav"]
    preserved = [target / "raw.wav", target / "chunk_123.wav", target / "chunk_01234.wav"]
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "raw.m4a").write_text("keep")
    (target / "linked").symlink_to(outside, target_is_directory=True)
    for path in matching + preserved:
        path.write_text("fixture")
    result = run("--", target.name, cwd=tmp_path)
    assert result.returncode == 0, result.stderr
    assert "found 2 matching" in result.stdout
    assert all(path.exists() for path in matching + preserved)
    result = run("--delete", "--", target.name, cwd=tmp_path)
    assert result.returncode == 0, result.stderr
    assert all(not path.exists() for path in matching)
    assert all(path.exists() for path in preserved)
    assert (outside / "raw.m4a").exists()


@pytest.mark.parametrize("args", [(".", "extra"), ("--", ".", "extra"), (".", "--", "extra")])
def test_rejects_extra_directories(tmp_path, args):
    assert run(*args, cwd=tmp_path).returncode == 2


def test_failed_discovery_prevents_partial_deletion(tmp_path):
    target = tmp_path / "raw.m4a"
    target.write_text("keep")
    tools = tmp_path / "bin"
    tools.mkdir()
    fake_find = tools / "find"
    fake_find.write_text('#!/bin/sh\nprintf "%s\\0" "$1/raw.m4a"\nexit 1\n')
    fake_find.chmod(0o755)
    result = run("--delete", str(tmp_path), cwd=tmp_path, env={**os.environ, "PATH": f"{tools}:{os.environ['PATH']}"})
    assert result.returncode != 0
    assert target.exists()
    assert "Deleted" not in result.stdout
