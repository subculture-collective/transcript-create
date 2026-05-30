"""Schema contract tests for workflow state columns."""

import pytest
from sqlalchemy import text


REQUIRED_COLUMNS = {
    "caption_ingest_state": {"data_type": "text", "is_nullable": "NO", "default_contains": "'pending'"},
    "caption_ingest_error": {"data_type": "text", "is_nullable": "YES", "default_contains": None},
    "diarization_state": {"data_type": "text", "is_nullable": "NO", "default_contains": "'pending'"},
    "diarization_error": {"data_type": "text", "is_nullable": "YES", "default_contains": None},
}

REQUIRED_CONSTRAINTS = {
    "videos_caption_ingest_state_check": {"pending", "running", "completed", "unavailable", "failed", "skipped"},
    "videos_diarization_state_check": {"pending", "running", "completed", "failed", "skipped"},
}


def _column_contract(db_session, table_name: str, column_name: str):
    result = db_session.execute(
        text(
            """
            SELECT data_type, is_nullable, column_default
            FROM information_schema.columns
            WHERE table_schema = 'public'
              AND table_name = :table_name
              AND column_name = :column_name
            """
        ),
        {"table_name": table_name, "column_name": column_name},
    )
    return result.mappings().first()


def _constraint_definition(db_session, table_name: str, constraint_name: str) -> str | None:
    result = db_session.execute(
        text(
            """
            SELECT pg_get_constraintdef(c.oid) AS definition
            FROM pg_constraint c
            JOIN pg_class t ON t.oid = c.conrelid
            JOIN pg_namespace n ON n.oid = t.relnamespace
            WHERE n.nspname = 'public'
              AND t.relname = :table_name
              AND c.conname = :constraint_name
            """
        ),
        {"table_name": table_name, "constraint_name": constraint_name},
    )
    row = result.mappings().first()
    return row["definition"] if row else None


def _allowed_values_from_check_definition(definition: str) -> set[str]:
    """Extract string literals from Postgres CHECK definitions for state columns."""
    values: set[str] = set()
    marker = "'"
    parts = definition.split(marker)
    for idx in range(1, len(parts), 2):
        values.add(parts[idx])
    return values


@pytest.mark.usefixtures("db_session")
def test_videos_schema_has_workflow_state_columns(db_session):
    for column, expected in REQUIRED_COLUMNS.items():
        contract = _column_contract(db_session, "videos", column)
        assert contract is not None, f"Missing videos.{column}"
        assert contract["data_type"] == expected["data_type"]
        assert contract["is_nullable"] == expected["is_nullable"]
        default_contains = expected["default_contains"]
        if default_contains is None:
            assert contract["column_default"] is None
        else:
            assert default_contains in (contract["column_default"] or "")


@pytest.mark.usefixtures("db_session")
def test_videos_schema_has_workflow_state_constraints(db_session):
    for constraint, allowed_values in REQUIRED_CONSTRAINTS.items():
        definition = _constraint_definition(db_session, "videos", constraint)
        assert definition is not None, f"Missing constraint {constraint}"
        assert _allowed_values_from_check_definition(definition) == allowed_values
