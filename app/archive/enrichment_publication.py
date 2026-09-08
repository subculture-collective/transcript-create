"""Explicit post-PR28 approval policy. Call within the owner's transaction.

Generation remains candidate-only until all generation/storage checks pass.
Publication uses the normal chapter review validator and preserves audit rows.
"""

from __future__ import annotations

import json
from typing import Any

from sqlalchemy import text

from .chapter_review import review_chapter_set
from .openrouter_enrichment import PROMPT_VERSION

QUALITY_CUTOFF = "2026-09-07T00:30:07Z"
APPROVAL_REASON = "User-authorized automatic approval of successful post-PR28 enrichment (2026-09-07)"


def approve_run(db: Any, run_id: str) -> dict[str, Any]:
    run = (
        db.execute(
            text("""SELECT * FROM archive_extraction_runs WHERE id=:id AND status='completed'
            AND model_name='deepseek/deepseek-v4-pro' AND prompt_version=:prompt
            AND started_at>=CAST(:cutoff AS timestamptz) FOR UPDATE"""),
            {"id": run_id, "prompt": PROMPT_VERSION, "cutoff": QUALITY_CUTOFF},
        )
        .mappings()
        .one_or_none()
    )
    if run is None:
        raise ValueError("Only successful post-PR28 DeepSeek runs may be approved")
    if db.execute(text("SELECT 1 FROM archive_enrichment_approvals WHERE run_id=:id"), {"id": run_id}).scalar():
        return {"status": "already_approved", "run_id": run_id}
    video_id = str(run["video_id"])
    db.execute(text("SELECT id FROM videos WHERE id=:id FOR UPDATE"), {"id": video_id})
    chapters = list(
        db.execute(
            text("SELECT * FROM archive_video_chapters WHERE video_id=:video ORDER BY chapter_index FOR UPDATE"),
            {"video": video_id},
        ).mappings()
    )
    assignments = list(
        db.execute(
            text("SELECT * FROM archive_label_assignments WHERE run_id=:id AND source='llm' ORDER BY id FOR UPDATE"),
            {"id": run_id},
        ).mappings()
    )
    metrics = run["metrics"] or {}
    if (
        not chapters
        or not assignments
        or metrics.get("repairs", {}).get("evidence_overlap_violations") != 0
        or len(chapters) != metrics.get("chapters")
        or len(assignments) != metrics.get("assignments")
        or not metrics.get("categories")
        or any(
            str(c["run_id"]) != run_id
            or c["status"] != "candidate"
            or c["source"] != "automatic"
            or c["created_at"] != c["updated_at"]
            for c in chapters
        )
        or any(
            str(a["video_id"]) != video_id or a["status"] != "candidate" or a["created_at"] != a["updated_at"]
            for a in assignments
        )
    ):
        raise ValueError("Approval refuses edited, conflicting or unvalidated candidates")
    if db.execute(
        text("""SELECT 1 FROM archive_chapter_feedback f WHERE video_id=:video
            AND NOT EXISTS (SELECT 1 FROM archive_enrichment_maintenance_rows m
                WHERE m.table_name='archive_chapter_feedback' AND m.row_id=f.id::text) LIMIT 1"""),
        {"video": video_id},
    ).scalar():
        raise ValueError("Approval refuses prior editorial chapter feedback")
    if db.execute(
        text("SELECT 1 FROM archive_label_feedback WHERE assignment_id=ANY(:ids) LIMIT 1"),
        {"ids": [a["id"] for a in assignments]},
    ).scalar():
        raise ValueError("Approval refuses prior assignment feedback")
    labels = list(
        db.execute(
            text("SELECT * FROM archive_labels WHERE id=ANY(:ids) ORDER BY id FOR UPDATE"),
            {"ids": list({a["label_id"] for a in assignments})},
        ).mappings()
    )
    if any(
        label["status"] not in {"candidate", "published", "hidden"} or label["canonical_id"] is not None
        for label in labels
    ):
        raise ValueError("Approval refuses rejected or merged labels")
    if any(label["status"] == "candidate" and label["source"] != "automatic" for label in labels):
        raise ValueError("Approval refuses unpublished editorial labels")
    hidden_ids = {label["id"] for label in labels if label["status"] == "hidden"}
    visible_category_ids = {
        label["id"] for label in labels if label["kind"] == "category" and label["id"] not in hidden_ids
    }
    if not any(a["label_id"] in visible_category_ids for a in assignments):
        raise ValueError("Approval requires a non-hidden sustained category")
    # Never publish a shared candidate label if that would expose unrelated
    # already-visible assignments without explicit approval for those rows.
    for label in labels:
        if (
            label["status"] == "candidate"
            and db.execute(
                text("SELECT 1 FROM archive_label_feedback WHERE label_id=:id LIMIT 1"), {"id": label["id"]}
            ).scalar()
        ):
            raise ValueError("Approval refuses prior editorial label feedback")
        if (
            label["status"] == "candidate"
            and db.execute(
                text("""SELECT 1 FROM archive_label_assignments
            WHERE label_id=:label AND run_id IS DISTINCT FROM CAST(:run AS uuid)
            AND status IN ('auto_published','admin_approved') LIMIT 1"""),
                {"label": label["id"], "run": run_id},
            ).scalar()
        ):
            raise ValueError("Approval would expose unrelated shared-label assignments")
    snapshot = {
        "chapters": [dict(c) for c in chapters],
        "assignments": [dict(a) for a in assignments],
        "labels": [dict(label) for label in labels],
    }
    db.execute(
        text(
            "INSERT INTO archive_enrichment_approvals(run_id,reason,snapshot) VALUES (:id,:reason,CAST(:snapshot AS jsonb))"
        ),
        {"id": run_id, "reason": APPROVAL_REASON, "snapshot": json.dumps(snapshot, default=str)},
    )
    published = review_chapter_set(db, video_id, action="publish", reason=APPROVAL_REASON)
    for label in labels:
        if label["status"] == "candidate":
            db.execute(
                text("UPDATE archive_labels SET status='published',updated_at=now() WHERE id=:id"), {"id": label["id"]}
            )
            _feedback(db, label["id"], None, {"status": "candidate"}, {"status": "published"})
    for assignment in assignments:
        if assignment["label_id"] in hidden_ids:
            continue
        db.execute(
            text("UPDATE archive_label_assignments SET status='admin_approved',updated_at=now() WHERE id=:id"),
            {"id": assignment["id"]},
        )
        _feedback(db, assignment["label_id"], assignment["id"], {"status": "candidate"}, {"status": "admin_approved"})
    suppressed = sum(a["label_id"] in hidden_ids for a in assignments)
    return {
        "status": "approved",
        "run_id": run_id,
        "chapters": len(published),
        "assignments": len(assignments) - suppressed,
        "suppressed_assignments": suppressed,
    }


def _feedback(db: Any, label_id: Any, assignment_id: Any, old: dict[str, Any], new: dict[str, Any]) -> None:
    db.execute(
        text("""INSERT INTO archive_label_feedback(label_id,assignment_id,action,old_value,new_value,reason)
        VALUES (:label,:assignment,'approve',CAST(:old AS jsonb),CAST(:new AS jsonb),:reason)"""),
        {
            "label": label_id,
            "assignment": assignment_id,
            "old": json.dumps(old),
            "new": json.dumps(new),
            "reason": APPROVAL_REASON,
        },
    )
