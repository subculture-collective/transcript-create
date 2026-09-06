from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import pytest
from sqlalchemy import text

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "compose_prod.sh"
VIDEO_ID = "9e0922f1-ff96-49f5-8279-beee25d7a8b0"
CONTAINER_ID = "a" * 64


@pytest.mark.parametrize("mutation", ["confidence", "timestamp", "alias", "unprotect"])
def test_protected_fingerprint_detects_database_mutations(db_session, mutation):
    result = subprocess.run(
        [
            "bash",
            "-c",
            f'source {SCRIPT}; psql_admin_sql() {{ printf "%s" "$1"; }}; '
            "enrichment_canary_protected_label_fingerprint",
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=True,
    )
    fingerprint_sql = text(result.stdout)
    label_id = db_session.execute(text("""
        INSERT INTO archive_labels (slug, label, kind, status, source, publish_tier, confidence_score, updated_at)
        VALUES ('fingerprint-regression', 'Fingerprint', 'topic', 'published', 'automatic', 'gold', 0.42,
                '2020-01-01'::timestamptz) RETURNING id
    """)).scalar_one()
    before = db_session.execute(fingerprint_sql).scalar_one()
    assert db_session.execute(fingerprint_sql).scalar_one() == before
    statements = {
        "confidence": "UPDATE archive_labels SET confidence_score = 0.99 WHERE id = :id",
        "timestamp": "UPDATE archive_labels SET updated_at = now() WHERE id = :id",
        "unprotect": "UPDATE archive_labels SET status = 'candidate' WHERE id = :id",
        "alias": "INSERT INTO archive_label_aliases (label_id, alias, normalized_alias, source) "
        "VALUES (:id, 'Alias', 'alias', 'automatic')",
    }
    db_session.execute(text(statements[mutation]), {"id": label_id})
    assert db_session.execute(fingerprint_sql).scalar_one() != before


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
enrichment_canary_protected_label_fingerprint() {{ printf 'abcdef0123456789abcdef0123456789\\n'; }}
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
    assert "protected_label_fingerprint" in preflight[0].read_text(encoding="utf-8")
    verification = next((tmp_path / "evidence").glob("*/protected-label-verification.json"))
    assert json.loads(verification.read_text())["protected_labels"] == "passed"


def test_enrichment_canary_rejects_protected_label_mutation(tmp_path: Path) -> None:
    body = f"""
enrichment_canary_protected_label_fingerprint() {{
  if [[ -f {tmp_path / 'snapshot-taken'} ]]; then
    printf 'ffffffffffffffffffffffffffffffff\\n'
  else
    touch {tmp_path / 'snapshot-taken'}
    printf '00000000000000000000000000000000\\n'
  fi
}}
run_enrichment_canary {VIDEO_ID}
"""
    result = _run_sourced(tmp_path, body)
    assert result.returncode != 0
    assert '"protected_labels":"failed"' in result.stdout
    assert "verified" not in (tmp_path / "marker").read_text()
    verification = next((tmp_path / "evidence").glob("*/protected-label-verification.json"))
    assert json.loads(verification.read_text())["protected_labels"] == "failed"


def test_enrichment_canary_invalid_protected_snapshot_prevents_provider_start(tmp_path: Path) -> None:
    result = _run_sourced(
        tmp_path,
        f"""
enrichment_canary_protected_label_fingerprint() {{ printf 'invalid\\n'; }}
run_enrichment_canary {VIDEO_ID}
""",
    )
    assert result.returncode != 0
    assert "compose:" not in (tmp_path / "marker").read_text()


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
    verification = next((tmp_path / "evidence").glob("*/protected-label-verification.json"))
    assert json.loads(verification.read_text())["protected_labels"] == "passed"


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


def test_enrichment_canary_acceptance_failure_does_not_double_cleanup_or_fence_completed_run(tmp_path: Path) -> None:
    body = f"""
cleanup_enrichment_canary_container() {{ printf 'cleanup\\n' >> {tmp_path / 'marker'}; }}
fence_enrichment_canary_run() {{ printf 'fence\\n' >> {tmp_path / 'marker'}; }}
verify_enrichment_canary_result() {{ printf 'acceptance-failed\\n' >> {tmp_path / 'marker'}; return 1; }}
run_enrichment_canary {VIDEO_ID}
"""
    result = _run_sourced(tmp_path, body)

    assert result.returncode != 0
    marker = (tmp_path / "marker").read_text(encoding="utf-8").splitlines()
    assert marker.count("cleanup") == 1
    assert "acceptance-failed" in marker
    assert "fence" not in marker


def test_enrichment_canary_signal_handler_cleans_then_fences(tmp_path: Path) -> None:
    body = f"""
enrichment_canary_started=true
enrichment_canary_evidence_dir={tmp_path}
enrichment_canary_protected_fingerprint=abcdef0123456789abcdef0123456789
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
    assert "archive enrichment canary acceptance failed; evidence preserved" in helper
    acceptance = helper.split("verify_enrichment_canary_result() {", 1)[1].split("\n}", 1)[0]
    assert "1 / CASE" not in acceptance
    assert "evidence_overlap_violations" in helper
    assert "chapter_coverage" in helper
    assert "ARCHIVE_ENRICHMENT_ENABLED=true" in canary
    assert "ARCHIVE_ENRICHMENT_PUBLISH=false" in canary
    assert "run_archive_enrichment_queue.py --once --video-id" in canary
    assert "compose start" not in canary
    assert "compose restart" not in canary


def test_parameterized_psql_uses_stdin_for_variable_interpolation(tmp_path: Path) -> None:
    result = subprocess.run(
        [
            "bash",
            "-c",
            f"""
source {SCRIPT}
psql_admin() {{ printf 'args:%s\\n' "$*"; cat; }}
psql_admin_sql "SELECT :'probe_value';" -At -v probe_value=safe-probe
""",
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert "args:-At -v probe_value=safe-probe -f -" in result.stdout
    assert "SELECT :'probe_value';" in result.stdout
    helper = SCRIPT.read_text(encoding="utf-8")
    for function_name in (
        "check_enrichment_canary_target",
        "check_enrichment_canary_guardrails",
        "enrichment_canary_assignment_fingerprint",
        "fence_enrichment_canary_run",
        "verify_enrichment_canary_result",
    ):
        function = helper.split(f"{function_name}() {{", 1)[1].split("\n}", 1)[0]
        assert "psql_admin_sql" in function
