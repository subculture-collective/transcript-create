#!/usr/bin/env python3
"""Compare essential schema contract between two PostgreSQL databases."""

import os
import sys
from typing import TypeAlias, TypeVar

import psycopg


ESSENTIAL_TABLES = (
    "jobs",
    "videos",
    "transcripts",
    "segments",
    "youtube_transcripts",
    "youtube_segments",
)

ESSENTIAL_COLUMNS_QUERY = """
SELECT table_name, column_name, data_type, is_nullable, column_default
FROM information_schema.columns
WHERE table_schema = 'public'
  AND table_name = ANY(%s)
ORDER BY table_name, ordinal_position
"""

VIDEO_CONSTRAINTS_QUERY = """
SELECT c.conname, pg_get_constraintdef(c.oid) AS definition
FROM pg_constraint c
JOIN pg_class t ON t.oid = c.conrelid
JOIN pg_namespace n ON n.oid = t.relnamespace
WHERE n.nspname = 'public' AND t.relname = 'videos'
  AND c.conname = ANY(%s)
ORDER BY c.conname
"""

REQUIRED_CONSTRAINTS = [
    "videos_caption_ingest_state_check",
    "videos_diarization_state_check",
]


SchemaRow: TypeAlias = tuple[str, str, str, str, str | None]
ConstraintRow: TypeAlias = tuple[str, str]
T = TypeVar("T", SchemaRow, ConstraintRow)


def _load_contract(conn: psycopg.Connection) -> tuple[list[SchemaRow], set[ConstraintRow]]:
    with conn.cursor() as cur:
        cur.execute(ESSENTIAL_COLUMNS_QUERY, (list(ESSENTIAL_TABLES),))
        columns = cur.fetchall()

        cur.execute(VIDEO_CONSTRAINTS_QUERY, (REQUIRED_CONSTRAINTS,))
        constraints = {(row[0], row[1]) for row in cur.fetchall()}
    return columns, constraints


def _print_set_diff(label: str, left: set[T], right: set[T]) -> None:
    left_only = sorted(left - right)
    right_only = sorted(right - left)
    if left_only:
        print(f"{label} left-only:", file=sys.stderr)
        for item in left_only:
            print(f"- {item}", file=sys.stderr)
    if right_only:
        print(f"{label} right-only:", file=sys.stderr)
        for item in right_only:
            print(f"- {item}", file=sys.stderr)


def main() -> int:
    left_url = os.environ.get("SCHEMA_LEFT_DATABASE_URL")
    right_url = os.environ.get("SCHEMA_RIGHT_DATABASE_URL")
    if not left_url or not right_url:
        print("SCHEMA_LEFT_DATABASE_URL and SCHEMA_RIGHT_DATABASE_URL are required", file=sys.stderr)
        return 1

    with psycopg.connect(left_url) as left_conn, psycopg.connect(right_url) as right_conn:
        left_columns, left_constraints = _load_contract(left_conn)
        right_columns, right_constraints = _load_contract(right_conn)

    required_constraint_names = set(REQUIRED_CONSTRAINTS)
    left_constraint_names = {name for name, _definition in left_constraints}
    right_constraint_names = {name for name, _definition in right_constraints}
    missing_left = required_constraint_names - left_constraint_names
    missing_right = required_constraint_names - right_constraint_names

    left_column_set = set(left_columns)
    right_column_set = set(right_columns)
    if left_column_set != right_column_set or left_constraints != right_constraints or missing_left or missing_right:
        print("Schema contract mismatch", file=sys.stderr)
        for name in sorted(missing_left):
            print(f"required video constraint missing on left: {name}", file=sys.stderr)
        for name in sorted(missing_right):
            print(f"required video constraint missing on right: {name}", file=sys.stderr)
        _print_set_diff("columns", left_column_set, right_column_set)
        _print_set_diff("video constraints", left_constraints, right_constraints)
        return 1

    print("Schema contract matches")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
