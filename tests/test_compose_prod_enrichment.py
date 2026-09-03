from __future__ import annotations

import os
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "compose_prod.sh"
VIDEO_ID = "9e0922f1-ff96-49f5-8279-beee25d7a8b0"
CONTAINER_ID = "a" * 64


def _fake_docker(tmp_path: Path, *, worker_status: int = 0) -> Path:
    docker = tmp_path / "docker"
    docker.write_text(
        f"""#!/usr/bin/env bash
set -eu
case "$*" in
  *"container inspect"*"{{{{.Id}}}}"*) printf '%s\\n' '{CONTAINER_ID}' ;;
  *"container wait"*) printf '%s\\n' '{worker_status}' ;;
  *"container logs"*) printf '%s\\n' '{{"status": "completed", "video_id": "{VIDEO_ID}"}}' ;;
  *"container ls"*) : ;;
  *"container stop"*|*"container rm"*) : ;;
  *) printf 'unexpected docker call: %s\\n' "$*" >&2; exit 97 ;;
esac
""",
        encoding="utf-8",
    )
    docker.chmod(0o755)
    return docker


def _run_sourced(
    tmp_path: Path,
    body: str,
    *,
    worker_status: int = 0,
    timeout_wait: bool = False,
) -> subprocess.CompletedProcess[str]:
    _fake_docker(tmp_path, worker_status=worker_status)
    marker = tmp_path / "marker"
    evidence = tmp_path / "evidence"
    timeout_override = ""
    if timeout_wait:
        timeout_override = """
timeout() {
  if [[ "$*" == *"container wait"* ]]; then return 124; fi
  command timeout "$@"
}
"""
    shell = f"""
source {SCRIPT}
{timeout_override}
run_preflight() {{ printf 'preflight\\n' >> {marker}; }}
assert_container_healthy() {{ printf 'healthy:%s\\n' "$1" >> {marker}; }}
assert_enrichment_queue_inert() {{ printf 'queue-inert\\n' >> {marker}; }}
check_enrichment_canary_target() {{ printf 'target-eligible\\n' >> {marker}; }}
check_enrichment_canary_guardrails() {{ printf 'guardrails-pass\\n' >> {marker}; }}
psql_admin() {{
  if [[ "$*" == *"clock_timestamp"* ]]; then printf '2026-09-03 12:00:00+00\\n'; else printf '0\\n'; fi
}}
enrichment_canary_assignment_fingerprint() {{ printf '0123456789abcdef0123456789abcdef\\n'; }}
compose() {{ printf 'compose:%s\\n' "$*" >> {marker}; }}
enrichment_container_details_match() {{ return 0; }}
verify_enrichment_canary_result() {{ printf 'verified\\n' >> {marker}; }}
enrichment_canary_evidence_root={evidence}
{body}
"""
    environment = {
        "PATH": f"{tmp_path}:/usr/bin:/bin",
        "HOME": os.environ.get("HOME", ""),
        "USER": os.environ.get("USER", ""),
    }
    return subprocess.run(
        ["bash", "-c", shell],
        cwd=ROOT,
        env=environment,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )


def test_enrichment_canary_wrapper_rejects_unsafe_arguments_without_docker(tmp_path: Path) -> None:
    for arguments in (
        ("maintenance", "archive-enrichment-canary"),
        ("maintenance", "archive-enrichment-canary", "not-a-uuid", "--approved"),
        ("maintenance", "archive-enrichment-canary", VIDEO_ID, "not-approved"),
        ("maintenance", "archive-enrichment-canary", VIDEO_ID, "--approved", "extra"),
    ):
        result = subprocess.run(
            ["bash", str(SCRIPT), *arguments],
            cwd=ROOT,
            env={"PATH": "/usr/bin:/bin", "HOME": os.environ.get("HOME", "")},
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        assert result.returncode == 64
        assert "archive-enrichment-canary requires exactly one UUID and --approved" in result.stderr


def test_enrichment_canary_wrapper_runs_one_exact_review_only_container(tmp_path: Path) -> None:
    result = _run_sourced(tmp_path, f"run_enrichment_canary {VIDEO_ID}")

    assert result.returncode == 0, result.stderr
    marker = (tmp_path / "marker").read_text(encoding="utf-8")
    assert marker.index("preflight") < marker.index("target-eligible") < marker.index("guardrails-pass")
    compose = next(line for line in marker.splitlines() if line.startswith("compose:"))
    for expected in (
        "run -d --no-deps",
        "ARCHIVE_ENRICHMENT_ENABLED=true",
        "ARCHIVE_ENRICHMENT_PUBLISH=false",
        "ARCHIVE_ENRICHMENT_MODEL=deepseek/deepseek-v4-pro",
        "ARCHIVE_ENRICHMENT_MAX_WINDOW_MINUTES=90",
        "ARCHIVE_ENRICHMENT_MAX_COST_USD_PER_VIDEO=1.00",
        "archive-enrichment-queue python3 /app/scripts/run_archive_enrichment_queue.py --once --video-id",
        VIDEO_ID,
    ):
        assert expected in compose
    assert "verified" in marker
    results = list((tmp_path / "evidence").glob("*/result.json"))
    assert len(results) == 1
    assert '"status": "completed"' in results[0].read_text(encoding="utf-8")
    preflight = list((tmp_path / "evidence").glob("*/preflight.json"))
    assert len(preflight) == 1
    assert "preexisting_assignment_fingerprint" in preflight[0].read_text(encoding="utf-8")


def test_enrichment_canary_nonzero_worker_is_cleaned_and_fenced(tmp_path: Path) -> None:
    body = f"""
cleanup_enrichment_canary_container() {{ printf 'cleanup\\n' >> {tmp_path / 'marker'}; }}
fence_enrichment_canary_run() {{ printf 'fence\\n' >> {tmp_path / 'marker'}; }}
run_enrichment_canary {VIDEO_ID}
"""
    result = _run_sourced(tmp_path, body, worker_status=7)

    assert result.returncode != 0
    marker = (tmp_path / "marker").read_text(encoding="utf-8")
    assert "cleanup" in marker
    assert "fence" in marker


def test_enrichment_canary_wait_timeout_is_cleaned_and_fenced(tmp_path: Path) -> None:
    body = f"""
cleanup_enrichment_canary_container() {{ printf 'cleanup\\n' >> {tmp_path / 'marker'}; }}
fence_enrichment_canary_run() {{ printf 'fence\\n' >> {tmp_path / 'marker'}; }}
run_enrichment_canary {VIDEO_ID}
"""
    result = _run_sourced(tmp_path, body, timeout_wait=True)

    assert result.returncode != 0
    marker = (tmp_path / "marker").read_text(encoding="utf-8")
    assert marker.splitlines()[-2:] == ["cleanup", "fence"]


def test_enrichment_canary_signal_handler_cleans_then_fences(tmp_path: Path) -> None:
    body = f"""
enrichment_canary_started=true
cleanup_enrichment_canary_container() {{ printf 'cleanup\\n' >> {tmp_path / 'marker'}; }}
fence_enrichment_canary_run() {{ printf 'fence\\n' >> {tmp_path / 'marker'}; }}
on_enrichment_canary_signal 143
"""
    result = _run_sourced(tmp_path, body)

    assert result.returncode == 143
    marker = (tmp_path / "marker").read_text(encoding="utf-8")
    assert marker.splitlines()[-2:] == ["cleanup", "fence"]


def test_enrichment_canary_contract_has_timeout_identity_and_acceptance_checks() -> None:
    helper = SCRIPT.read_text(encoding="utf-8")
    canary = helper.split("run_enrichment_canary() {", 1)[1].split("\n}\n\n[[", 1)[0]

    assert "timeout --signal=TERM --kill-after=30s 20m" in canary
    assert "hasanara.enrichment-canary-token" in helper
    assert "hasanara-archive-enrichment-canary" in helper
    assert "duration_seconds > 5400 AND v.duration_seconds <= 10800" in helper
    assert "metrics ->> 'window_count'" in helper
    assert "metrics ->> 'categories'" in helper
    assert "evidence_overlap_violations" in helper
    assert "chapter_coverage" in helper
    assert "ARCHIVE_ENRICHMENT_ENABLED=true" in canary
    assert "ARCHIVE_ENRICHMENT_PUBLISH=false" in canary
    assert "run_archive_enrichment_queue.py --once --video-id" in canary
    assert "compose start" not in canary
    assert "compose restart" not in canary
