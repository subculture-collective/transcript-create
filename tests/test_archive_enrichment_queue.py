from __future__ import annotations

from pathlib import Path

from scripts.run_archive_enrichment_queue import QueueDependencies, main, run_queue_cycle, select_next_video

ROOT = Path(__file__).resolve().parents[1]


def test_queue_cycle_enriches_one_selected_video() -> None:
    calls: list[tuple[object, str]] = []
    db = object()
    dependencies = QueueDependencies(
        select_video=lambda session, model, prompt, cooldown: "video-1",
        enrich_video=lambda session, video_id: calls.append((session, video_id))
        or {"chapters": 12, "cost_usd": 0.23},
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

    assert main(
        ["--once"],
        config=_Config(),
        dependencies=QueueDependencies(
            select_video=lambda session, model, prompt, cooldown: None,
            enrich_video=lambda session, video_id: {},
        ),
    ) == 0

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
    assert '"archive-enrichment-queue": "api"' in preflight
