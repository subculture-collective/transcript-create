from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

from scripts.run_archive_enrichment_queue import (
    QueueDependencies,
    QueueGuardrailSnapshot,
    evaluate_queue_guardrails,
    main,
    run_queue_cycle,
    select_next_video,
    select_requested_video,
)

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize("phase", ["selected", "idle", "paused"])
def test_continuous_signal_stops_before_next_video(monkeypatch, phase):
    from types import SimpleNamespace

    from scripts import run_archive_enrichment_queue as cli

    handlers = {}
    finished = []
    selected = []
    monkeypatch.setattr(cli.signal, "signal", lambda number, handler: handlers.setdefault(number, handler))
    monkeypatch.setattr(cli, "SessionLocal", lambda: SimpleNamespace(close=lambda: None))
    monkeypatch.setattr(cli, "discover_jobs", lambda *_args: None)
    monkeypatch.setattr(
        cli, "next_job", lambda *_args: selected.append(phase) or {"status": phase, "video_id": "video-1"}
    )
    monkeypatch.setattr(cli, "finish_job", lambda *_args: finished.append(True))

    def stop(*_args):
        handlers[cli.signal.SIGTERM](cli.signal.SIGTERM, None)
        return {"chapters": 2}

    config = SimpleNamespace(ARCHIVE_ENRICHMENT_ENABLED=True, ARCHIVE_ENRICHMENT_MODEL="test")
    assert (
        cli.main(
            ["--continuous"],
            config=config,
            sleeper=stop,
            dependencies=QueueDependencies(select_video=lambda *_args: None, enrich_video=stop),
        )
        == 0
    )
    assert selected == [phase]
    assert len(finished) == (1 if phase == "selected" else 0)


@pytest.mark.parametrize(
    "arguments",
    [
        ["--continuous", "--once"],
        ["--resume-queue"],
        ["--queue-status"],
        ["--once", "--queue-status", "--resume-queue"],
    ],
)
def test_queue_maintenance_rejects_ambiguous_arguments(arguments):
    from types import SimpleNamespace

    with pytest.raises(SystemExit) as exc:
        main(
            arguments,
            config=SimpleNamespace(ARCHIVE_ENRICHMENT_ENABLED=False),
            dependencies=QueueDependencies(select_video=lambda *_args: None, enrich_video=lambda *_args: {}),
        )
    assert exc.value.code == 2


def test_queue_cycle_enriches_one_selected_video() -> None:
    calls: list[tuple[object, str]] = []
    db = object()
    dependencies = QueueDependencies(
        select_video=lambda session, model, prompt, cooldown: "video-1",
        enrich_video=lambda session, video_id: calls.append((session, video_id)) or {"chapters": 12, "cost_usd": 0.23},
    )

    result = run_queue_cycle(
        db,
        model="deepseek/deepseek-v4-pro",
        prompt_version="archive-episode-enrichment-v7",
        failure_cooldown_seconds=3600,
        dependencies=dependencies,
    )

    assert result == {
        "status": "completed",
        "video_id": "video-1",
        "metrics": {"chapters": 12, "cost_usd": 0.23},
    }
    assert calls == [(db, "video-1")]


def test_queue_cycle_reports_credit_exhaustion_without_raising() -> None:
    handled: list[tuple[object, str, str]] = []
    db = object()

    def exhausted(_session: object, _video_id: str) -> dict[str, object]:
        raise RuntimeError('OpenRouter request failed: HTTP 402: {"error":"Insufficient credits"}')

    result = run_queue_cycle(
        db,
        model="deepseek/deepseek-v4-pro",
        prompt_version="archive-episode-enrichment-v7",
        failure_cooldown_seconds=3600,
        dependencies=QueueDependencies(
            select_video=lambda session, model, prompt, cooldown: "video-2",
            enrich_video=exhausted,
            on_credit_exhausted=lambda session, video_id, model: handled.append((session, video_id, model)),
        ),
    )

    assert result == {"status": "credit_exhausted", "video_id": "video-2"}
    assert handled == [(db, "video-2", "deepseek/deepseek-v4-pro")]


def test_queue_cycle_reports_video_failure_so_the_daemon_can_continue() -> None:
    def invalid(_session: object, _video_id: str) -> dict[str, object]:
        raise ValueError("no exportable transcript blocks were found")

    result = run_queue_cycle(
        object(),
        model="deepseek/deepseek-v4-pro",
        prompt_version="archive-episode-enrichment-v7",
        failure_cooldown_seconds=3600,
        dependencies=QueueDependencies(
            select_video=lambda session, model, prompt, cooldown: "video-3",
            enrich_video=invalid,
        ),
    )

    assert result == {
        "status": "failed",
        "video_id": "video-3",
        "error": "no exportable transcript blocks were found",
    }


def test_selector_binds_current_provenance_and_failure_cooldown() -> None:
    captured: dict[str, object] = {}

    class _Result:
        def scalar_one_or_none(self) -> str:
            return "video-4"

    class _Db:
        def execute(self, statement: object, params: dict[str, object]) -> _Result:
            captured["statement"] = str(statement)
            captured["params"] = params
            return _Result()

    assert select_next_video(_Db(), "model-v1", "prompt-v2", 7200) == "video-4"
    assert captured["params"] == {
        "model": "model-v1",
        "prompt": "prompt-v2",
        "failure_cooldown_seconds": 7200,
    }


def test_requested_selector_requires_pristine_exact_video() -> None:
    captured: dict[str, object] = {}

    class _Result:
        def scalar_one_or_none(self) -> str:
            return "550e8400-e29b-41d4-a716-446655440000"

    class _Db:
        def execute(self, statement: object, params: dict[str, object]) -> _Result:
            captured["statement"] = str(statement)
            captured["params"] = params
            return _Result()

    video_id = "550e8400-e29b-41d4-a716-446655440000"
    assert select_requested_video(_Db(), "model-v1", "prompt-v2", 7200, video_id) == video_id
    sql = str(captured["statement"])
    assert "v.id = CAST(:video_id AS uuid)" in sql
    assert "archive_video_chapters" in sql
    assert "archive_label_assignments" in sql
    assert "assignment.source = 'llm'" in sql
    assert captured["params"] == {
        "video_id": video_id,
        "model": "model-v1",
        "prompt": "prompt-v2",
        "failure_cooldown_seconds": 7200,
    }


def test_queue_guardrails_fail_closed_on_attempt_cost_and_failure_limits() -> None:
    base = dict(max_attempts_24h=20, max_cost_usd_24h=5.0, failure_window=20, max_failure_rate=0.25)

    assert evaluate_queue_guardrails(QueueGuardrailSnapshot(20, 1.0, 10, 0), **base)["reason"] == "attempt_limit_24h"
    assert evaluate_queue_guardrails(QueueGuardrailSnapshot(10, 5.0, 10, 0), **base)["reason"] == "cost_limit_24h"
    failure_result = evaluate_queue_guardrails(QueueGuardrailSnapshot(10, 1.0, 20, 5), **base)
    assert failure_result == {
        "status": "guardrail_halted",
        "reason": "failure_rate",
        "guardrails": {
            "attempts_24h": 10,
            "recorded_cost_usd_24h": 1.0,
            "recent_finished": 20,
            "recent_failures": 5,
            "recent_failure_rate": 0.25,
        },
    }
    assert evaluate_queue_guardrails(QueueGuardrailSnapshot(10, 1.0, 19, 10), **base) is None


def test_once_cli_halts_before_selecting_video_when_guardrail_trips(monkeypatch, capsys) -> None:
    class _Db:
        closed = False

        def close(self) -> None:
            self.closed = True

    class _Config:
        ARCHIVE_ENRICHMENT_ENABLED = True
        ARCHIVE_ENRICHMENT_MODEL = "model-v1"
        ARCHIVE_ENRICHMENT_QUEUE_FAILURE_COOLDOWN_SECONDS = 7200
        ARCHIVE_ENRICHMENT_QUEUE_MAX_ATTEMPTS_PER_24H = 20
        ARCHIVE_ENRICHMENT_QUEUE_MAX_COST_USD_PER_24H = 5.0
        ARCHIVE_ENRICHMENT_QUEUE_FAILURE_WINDOW = 20
        ARCHIVE_ENRICHMENT_QUEUE_MAX_FAILURE_RATE = 0.25

    db = _Db()
    selected: list[str] = []
    monkeypatch.setattr("scripts.run_archive_enrichment_queue.SessionLocal", lambda: db)

    assert (
        main(
            ["--once"],
            config=_Config(),
            dependencies=QueueDependencies(
                select_video=lambda *_args: selected.append("selected") or "video-1",
                enrich_video=lambda *_args: {},
                load_guardrail_snapshot=lambda *_args: QueueGuardrailSnapshot(20, 1.0, 10, 0),
            ),
        )
        == 0
    )

    assert selected == []
    assert db.closed
    output = capsys.readouterr().out.strip()
    assert '"status": "guardrail_halted"' in output
    assert '"reason": "attempt_limit_24h"' in output


def test_once_cli_reports_idle_and_closes_the_database(monkeypatch, capsys) -> None:
    class _Db:
        closed = False

        def close(self) -> None:
            self.closed = True

    class _Config:
        ARCHIVE_ENRICHMENT_ENABLED = True
        ARCHIVE_ENRICHMENT_MODEL = "model-v1"
        ARCHIVE_ENRICHMENT_QUEUE_FAILURE_COOLDOWN_SECONDS = 7200

    db = _Db()
    monkeypatch.setattr("scripts.run_archive_enrichment_queue.SessionLocal", lambda: db)

    assert (
        main(
            ["--once"],
            config=_Config(),
            dependencies=QueueDependencies(
                select_video=lambda session, model, prompt, cooldown: None,
                enrich_video=lambda session, video_id: {},
            ),
        )
        == 0
    )

    assert db.closed
    assert capsys.readouterr().out.strip() == '{"status": "idle"}'


def test_once_cli_is_inert_when_enrichment_is_disabled(monkeypatch, capsys) -> None:
    class _Config:
        ARCHIVE_ENRICHMENT_ENABLED = False
        ARCHIVE_ENRICHMENT_MODEL = "model-v1"
        ARCHIVE_ENRICHMENT_QUEUE_FAILURE_COOLDOWN_SECONDS = 7200

    monkeypatch.setattr(
        "scripts.run_archive_enrichment_queue.SessionLocal",
        lambda: (_ for _ in ()).throw(AssertionError("disabled queue must not open the database")),
    )

    assert main(["--once"], config=_Config()) == 0
    assert capsys.readouterr().out.strip() == '{"status": "disabled"}'


def test_video_id_requires_once_and_canonical_uuid(capsys) -> None:
    with pytest.raises(SystemExit) as missing_once:
        main(["--video-id", "550e8400-e29b-41d4-a716-446655440000"])
    assert missing_once.value.code == 2
    assert "--video-id requires --once" in capsys.readouterr().err

    with pytest.raises(SystemExit) as malformed:
        main(["--once", "--video-id", "not-a-uuid"])
    assert malformed.value.code == 2
    assert "must be a valid UUID" in capsys.readouterr().err


def test_requested_once_returns_nonzero_without_enriching_ineligible_video(monkeypatch, capsys) -> None:
    class _Db:
        closed = False

        def close(self) -> None:
            self.closed = True

    class _Config:
        ARCHIVE_ENRICHMENT_ENABLED = True
        ARCHIVE_ENRICHMENT_MODEL = "model-v1"
        ARCHIVE_ENRICHMENT_QUEUE_FAILURE_COOLDOWN_SECONDS = 7200

    db = _Db()
    enriched: list[str] = []
    monkeypatch.setattr("scripts.run_archive_enrichment_queue.SessionLocal", lambda: db)
    video_id = "550e8400-e29b-41d4-a716-446655440000"
    result = main(
        ["--once", "--video-id", video_id],
        config=_Config(),
        dependencies=QueueDependencies(
            select_video=lambda *_args: (_ for _ in ()).throw(AssertionError("automatic selector called")),
            select_requested_video=lambda *_args: None,
            enrich_video=lambda _db, selected: enriched.append(selected) or {},
        ),
    )

    assert result == 1
    assert enriched == []
    assert db.closed
    assert capsys.readouterr().out.strip() == f'{{"status": "ineligible", "video_id": "{video_id}"}}'


def test_requested_once_returns_nonzero_when_guardrail_halts_before_selection(monkeypatch, capsys) -> None:
    class _Db:
        def close(self) -> None:
            pass

    class _Config:
        ARCHIVE_ENRICHMENT_ENABLED = True
        ARCHIVE_ENRICHMENT_MODEL = "model-v1"
        ARCHIVE_ENRICHMENT_QUEUE_FAILURE_COOLDOWN_SECONDS = 7200
        ARCHIVE_ENRICHMENT_QUEUE_MAX_ATTEMPTS_PER_24H = 20
        ARCHIVE_ENRICHMENT_QUEUE_MAX_COST_USD_PER_24H = 5.0
        ARCHIVE_ENRICHMENT_QUEUE_FAILURE_WINDOW = 20
        ARCHIVE_ENRICHMENT_QUEUE_MAX_FAILURE_RATE = 0.25

    selected: list[str] = []
    monkeypatch.setattr("scripts.run_archive_enrichment_queue.SessionLocal", _Db)
    result = main(
        ["--once", "--video-id", "550e8400-e29b-41d4-a716-446655440000"],
        config=_Config(),
        dependencies=QueueDependencies(
            select_video=lambda *_args: None,
            select_requested_video=lambda *_args: selected.append("selected") or None,
            enrich_video=lambda *_args: {},
            load_guardrail_snapshot=lambda *_args: QueueGuardrailSnapshot(20, 1.0, 10, 0),
        ),
    )

    assert result == 1
    assert selected == []
    assert '"status": "guardrail_halted"' in capsys.readouterr().out


def test_compose_runs_enrichment_queue_as_a_guarded_api_service() -> None:
    base = (ROOT / "docker-compose.yml").read_text()
    production = (ROOT / "docker-compose.prod.yml").read_text()
    release = (ROOT / "docker-compose.release.yml").read_text()
    preflight = (ROOT / "scripts/release_preflight.py").read_text()

    service = base.split("    archive-enrichment-queue:", 1)[1].split("\n    opensearch:", 1)[0]
    assert "run_archive_enrichment_queue.py" in service
    assert "healthcheck:\n            disable: true" in service
    assert "restart: unless-stopped" in service
    assert "  archive-enrichment-queue:" in production
    assert "    archive-enrichment-queue:" in release
    assert "run_archive_enrichment_queue.py', '${ARCHIVE_ENRICHMENT_QUEUE_MODE:---once}'" in release
    assert '"archive-enrichment-queue": "api"' in preflight


def test_api_image_packages_the_enrichment_queue_entrypoint() -> None:
    dockerfile = (ROOT / "Dockerfile.api").read_text()

    assert "COPY scripts/run_archive_enrichment_queue.py ./scripts/run_archive_enrichment_queue.py" in dockerfile


def test_queue_entrypoint_runs_standalone_outside_the_repository() -> None:
    environment = os.environ.copy()
    environment.pop("PYTHONPATH", None)
    environment["ARCHIVE_ENRICHMENT_ENABLED"] = "false"

    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts/run_archive_enrichment_queue.py"), "--once"],
        cwd="/tmp",
        env=environment,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == '{"status": "disabled"}'
