from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
from typing import get_args

from app.archive.labeling import (
    AssignmentSource,
    AssignmentStatus,
    CandidateSignal,
    ChapterSource,
    ChapterStatus,
    ExtractionTier,
    LabelCandidate,
    LabelKind,
    LabelSource,
    LabelStatus,
    PublishTier,
    RunScope,
    TranscriptSource,
    UnitType,
)


MIGRATION_PATH = Path(__file__).resolve().parent.parent / "alembic" / "versions" / "20260604_2300_add_label_extraction_system.py"


def _load_migration_module():
    spec = spec_from_file_location("label_extraction_migration", MIGRATION_PATH)
    assert spec is not None and spec.loader is not None
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_labeling_types_expose_contract_literals_and_dataclasses():
    assert set(get_args(RunScope)) == {"video", "batch", "period", "backfill"}
    assert set(get_args(ExtractionTier)) == {"cheap", "balanced", "premium"}
    assert set(get_args(LabelKind)) == {"topic", "person", "series", "category", "event", "game", "org", "meme", "place", "issue"}
    assert set(get_args(LabelStatus)) == {"candidate", "review", "published", "hidden", "rejected", "merged"}
    assert set(get_args(LabelSource)) == {"admin", "automatic", "hybrid", "seed"}
    assert set(get_args(PublishTier)) == {"gold", "silver", "bronze", "shadow"}
    assert set(get_args(TranscriptSource)) == {"whisper", "youtube"}
    assert set(get_args(ChapterStatus)) == {"candidate", "published", "rejected", "hidden"}
    assert set(get_args(ChapterSource)) == {"automatic", "manual", "hybrid"}
    assert set(get_args(UnitType)) == {"vod", "chapter", "window", "segment"}
    assert set(get_args(AssignmentStatus)) == {"candidate", "auto_published", "admin_approved", "rejected", "shadow"}
    assert set(get_args(AssignmentSource)) == {"alias", "keyphrase", "search", "title", "embedding_cluster", "llm", "metadata", "admin", "hybrid"}

    signal = CandidateSignal(source="title", label="okbuddy", alias="okbuddy", score=0.9, evidence={"video_id": "v1"})
    candidate = LabelCandidate(label="okbuddy", kind="topic", aliases=("ok buddy",), confidence_score=0.95)

    assert signal.label == "okbuddy"
    assert candidate.component_scores == {}
    assert candidate.evidence == ()


def test_labeling_migration_exports_expected_revision_contract():
    migration = _load_migration_module()

    assert migration.revision == "20260604_2300_label_extraction"
    assert migration.down_revision == "20260604_2100_recurring_periods"


def test_labeling_migration_contains_expected_schema_contract():
    source = MIGRATION_PATH.read_text()

    expected_tables = [
        "archive_extraction_runs",
        "archive_labels",
        "archive_transcript_windows",
        "archive_video_chapters",
        "archive_label_aliases",
        "archive_label_assignments",
        "archive_label_feedback",
        "archive_label_policies",
    ]
    for table in expected_tables:
        assert f'"{table}"' in source

    expected_checks = [
        "archive_extraction_runs_scope_check",
        "archive_extraction_runs_extraction_tier_check",
        "archive_extraction_runs_status_check",
        "archive_labels_kind_check",
        "archive_labels_status_check",
        "archive_labels_source_check",
        "archive_labels_publish_tier_check",
        "archive_transcript_windows_source_check",
        "archive_video_chapters_status_check",
        "archive_video_chapters_source_check",
        "archive_label_aliases_source_check",
        "archive_label_aliases_status_check",
        "archive_label_assignments_unit_type_check",
        "archive_label_assignments_status_check",
        "archive_label_assignments_source_check",
        "archive_label_assignments_publish_tier_check",
        "archive_label_policies_label_kind_check",
        "archive_label_policies_unit_type_check",
        "archive_label_policies_extraction_tier_check",
    ]
    for constraint_name in expected_checks:
        assert constraint_name in source

    assert "assignment_key" in source
    assert "unique=True" in source
    assert "archive_label_assignments_public_idx" in source
    assignments_table_source = source.split('"archive_label_assignments"', 1)[1].split('"archive_label_feedback"', 1)[0]
    assert 'sa.Column("source", sa.Text(), nullable=False, server_default=sa.text("\'automatic\'"))' not in assignments_table_source
    assert 'sa.Column("source", sa.Text(), nullable=False)' in assignments_table_source
    assert "quality_tier" not in source
    assert "extraction_tier" in source
