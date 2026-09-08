"""Fixed-scope, snapshot-first cleanup of pre-PR28 model-generated rows."""

from __future__ import annotations

from typing import Any

from sqlalchemy import text

from .enrichment_publication import QUALITY_CUTOFF


def cleanup_legacy(db: Any) -> dict[str, Any]:
    params = {"cutoff": QUALITY_CUTOFF}
    db.execute(
        text("""CREATE TEMP TABLE legacy_chapters ON COMMIT DROP AS
        SELECT c.id FROM archive_video_chapters c JOIN archive_extraction_runs r ON r.id=c.run_id
        WHERE r.model_name IS NOT NULL AND r.started_at<CAST(:cutoff AS timestamptz)"""),
        params,
    )
    db.execute(
        text("""CREATE TEMP TABLE legacy_assignments ON COMMIT DROP AS
        SELECT a.id FROM archive_label_assignments a JOIN archive_extraction_runs r ON r.id=a.run_id
        WHERE a.source='llm' AND r.model_name IS NOT NULL AND r.started_at<CAST(:cutoff AS timestamptz)"""),
        params,
    )
    db.execute(text("""SELECT id FROM videos WHERE id IN (
        SELECT c.video_id FROM archive_video_chapters c JOIN legacy_chapters t ON t.id=c.id
        UNION SELECT a.video_id FROM archive_label_assignments a JOIN legacy_assignments t ON t.id=a.id)
        ORDER BY id FOR UPDATE"""))
    db.execute(text("SELECT c.id FROM archive_video_chapters c JOIN legacy_chapters t ON t.id=c.id FOR UPDATE OF c"))
    db.execute(
        text("SELECT a.id FROM archive_label_assignments a JOIN legacy_assignments t ON t.id=a.id FOR UPDATE OF a")
    )
    if db.execute(text("""SELECT 1 FROM archive_label_assignments a JOIN legacy_chapters c ON c.id=a.chapter_id
        WHERE NOT EXISTS(SELECT 1 FROM legacy_assignments t WHERE t.id=a.id) LIMIT 1""")).scalar():
        raise ValueError("Legacy chapter has an out-of-scope dependent assignment; refuse cascade deletion")
    batch = db.execute(
        text(
            """INSERT INTO archive_enrichment_maintenance(operation,reason)
        VALUES ('pre_pr28_cleanup','User authorized removing all pre-PR28 model chapters and LLM assignments, including previously published rows; preserve source data and audit history') RETURNING id"""
        )
    ).scalar_one()
    snapshots = {
        "archive_video_chapters": "r.id IN (SELECT id FROM legacy_chapters)",
        "archive_label_assignments": "r.id IN (SELECT id FROM legacy_assignments)",
        "archive_chapter_feedback": "r.chapter_id IN (SELECT id FROM legacy_chapters)",
        "archive_label_feedback": "r.assignment_id IN (SELECT id FROM legacy_assignments)",
    }
    counts = {}
    for table, predicate in snapshots.items():
        result = db.execute(
            text(f"""INSERT INTO archive_enrichment_maintenance_rows(batch_id,table_name,row_id,row_data)
            SELECT :batch,:table,r.id::text,to_jsonb(r) FROM {table} r WHERE {predicate}"""),
            {"batch": batch, "table": table},
        )
        counts[table] = result.rowcount
    removed = db.execute(text("DELETE FROM archive_label_assignments WHERE id IN (SELECT id FROM legacy_assignments)"))
    if removed.rowcount != counts["archive_label_assignments"]:
        raise ValueError("Legacy assignment cohort changed")
    removed = db.execute(text("""DELETE FROM archive_video_chapters c WHERE id IN (SELECT id FROM legacy_chapters)
        AND NOT EXISTS(SELECT 1 FROM archive_label_assignments a WHERE a.chapter_id=c.id)"""))
    if removed.rowcount != counts["archive_video_chapters"]:
        raise ValueError("Legacy chapter cohort changed or gained dependencies")
    # Feedback rows survive via ON DELETE SET NULL. Original links remain in
    # snapshot rows for recovery. Labels, runs, jobs and transcripts are untouched.
    return {"batch_id": str(batch), "snapshots": counts}
