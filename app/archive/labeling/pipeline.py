from __future__ import annotations

from typing import Any

from sqlalchemy import text

from .extractors import extract_alias_candidates, extract_keyphrase_candidates, extract_title_alias_candidates
from .normalization import slugify_label
from .policy import classify_candidate
from .repository import (
    ASSIGNMENT_SOURCES,
    create_extraction_run,
    finish_extraction_run,
    insert_assignment,
    upsert_label_candidate,
)
from .windows import build_windows_from_segments, load_source_segments, persist_windows

_DEFAULT_POLICY: dict[str, Any] = {
    "min_publish_score": 0.90,
    "min_review_score": 0.65,
    "min_evidence_count": 2,
    "min_distinct_videos": 1,
    "require_existing_canonical": False,
    "auto_publish_enabled": True,
}


def _fetch_all_dicts(result: Any) -> list[dict]:
    if hasattr(result, "mappings"):
        return [dict(row) for row in result.mappings().all()]
    if hasattr(result, "all"):
        return [dict(row) for row in result.all()]
    first = result.first() if hasattr(result, "first") else None
    return [] if first is None else [dict(first)]


def _fetch_first_dict(result: Any) -> dict | None:
    if hasattr(result, "mappings"):
        row = result.mappings().first()
    elif hasattr(result, "first"):
        row = result.first()
    else:
        row = None
    return None if row is None else dict(row)


def _table_columns(db: Any, table_name: str) -> set[str]:
    try:
        result = db.execute(
            text(
                """
                SELECT column_name
                FROM information_schema.columns
                WHERE table_name = :table_name
                """
            ),
            {"table_name": table_name},
        )
        return {str(row["column_name"] if isinstance(row, dict) else row[0]) for row in _fetch_all_dicts(result)}
    except Exception:
        return set()


def _load_existing_aliases(db: Any) -> list[dict]:
    alias_columns = _table_columns(db, "archive_label_aliases")
    select_columns = [
        "l.id AS label_id",
        "l.label",
        "l.kind",
        "l.status AS label_status",
        "a.alias",
        "a.normalized_alias",
    ]
    if "status" in alias_columns:
        select_columns.append("a.status AS status")
    if "is_ambiguous" in alias_columns:
        select_columns.append("a.is_ambiguous AS is_ambiguous")

    where_clauses = ["l.status IN ('published', 'candidate', 'review')"]
    if "status" in alias_columns:
        where_clauses.append("a.status = 'active'")

    statement = text(
        f"""
        SELECT {', '.join(select_columns)}
        FROM archive_labels AS l
        JOIN archive_label_aliases AS a ON a.label_id = l.id
        WHERE {' AND '.join(where_clauses)}
        ORDER BY l.label, a.alias
        """
    )
    result = db.execute(statement)
    return _fetch_all_dicts(result)


def _load_policy(db: Any, label_kind: str, unit_type: str, extraction_tier: str) -> dict:
    statement = text(
        """
        SELECT *
        FROM archive_label_policies
        WHERE label_kind = :label_kind
          AND unit_type = :unit_type
          AND extraction_tier = :extraction_tier
        LIMIT 1
        """
    )
    result = db.execute(
        statement,
        {"label_kind": label_kind, "unit_type": unit_type, "extraction_tier": extraction_tier},
    )
    row = _fetch_first_dict(result)
    if row is None:
        return dict(_DEFAULT_POLICY)
    policy = dict(_DEFAULT_POLICY)
    policy.update(row)
    return policy


def _candidate_existing_canonical(candidate: Any) -> bool:
    evidence = getattr(candidate, "evidence", ()) or ()
    for item in evidence:
        if str(item.get("extractor") or "").lower() in {"alias", "title"}:
            return True
    return False


def _coerce_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    return int(value)


def _load_video_title(db: Any, video_id: str) -> str:
    row = _fetch_first_dict(db.execute(text("SELECT title FROM videos WHERE id = :video_id"), {"video_id": video_id}))
    return str(row.get("title") or "") if row else ""


def extract_labels_for_video(
    db: Any,
    video_id: str,
    extraction_tier: str = "cheap",
    *,
    title_only: bool = False,
    include_keyphrases: bool = True,
    run_id: str | None = None,
) -> dict:
    run_scope = "video_title" if title_only else "video"
    if run_id is None:
        run_id = create_extraction_run(
            db,
            scope=run_scope,
            extraction_tier=extraction_tier,
            video_id=video_id,
            model_name="deterministic",
        )
    metrics = {"windows": 0, "candidates": 0, "assignments": 0}

    try:
        window_dicts: list[dict] = []
        if not title_only:
            for source in ("whisper", "youtube"):
                segments = load_source_segments(db, video_id, source)
                windows = build_windows_from_segments(segments, source=source)
                persist_windows(db, video_id, windows)
                metrics["windows"] += len(windows)
                window_dicts.extend(
                    {
                        "id": window.text_hash,
                        "video_id": video_id,
                        "source": source,
                        "text": window.text,
                        "start_ms": window.start_ms,
                        "end_ms": window.end_ms,
                    }
                    for window in windows
                )

        aliases = _load_existing_aliases(db)
        candidates = [] if title_only else extract_alias_candidates(window_dicts, aliases)
        title = _load_video_title(db, video_id)
        candidates.extend(extract_title_alias_candidates({"id": video_id, "title": title}, aliases))
        if include_keyphrases and not title_only:
            candidates.extend(extract_keyphrase_candidates(window_dicts, min_distinct_videos=1, min_occurrences=3))
        metrics["candidates"] = len(candidates)

        # Parallel workers upsert many of the same automatic labels. Sort by
        # slug so every transaction takes per-label advisory locks in the same
        # order, avoiding lock-order deadlocks across workers.
        candidates.sort(key=lambda candidate: (slugify_label(candidate.label), candidate.kind, candidate.label))

        for candidate in candidates:
            evidence = list(candidate.evidence)
            distinct_videos = len({str(item.get("video_id") or "") for item in evidence if item.get("video_id")})
            policy = _load_policy(db, candidate.kind, "window", extraction_tier)
            existing_canonical = _candidate_existing_canonical(candidate)
            publish_tier, assignment_status = classify_candidate(
                {
                    "label": candidate.label,
                    "kind": candidate.kind,
                    "unit_type": "window",
                    "confidence_score": candidate.confidence_score,
                    "evidence_count": len(evidence),
                    "distinct_videos": distinct_videos,
                    "source": str(evidence[0].get("extractor") or "hybrid") if evidence else "hybrid",
                },
                policy,
                existing_canonical=existing_canonical,
            )

            label_status = "published" if assignment_status == "auto_published" else "candidate"
            label_id = upsert_label_candidate(
                db,
                label=candidate.label,
                kind=candidate.kind,
                aliases=list(candidate.aliases),
                confidence_score=candidate.confidence_score,
                source="automatic",
                publish_tier=publish_tier,
                status=label_status,
                run_id=run_id,
            )

            label_row = _fetch_first_dict(
                db.execute(
                    text("SELECT status, canonical_id FROM archive_labels WHERE id = :label_id"),
                    {"label_id": label_id},
                )
            )
            if label_row and str(label_row.get("status") or "").lower() in {"rejected", "merged", "hidden"}:
                continue

            for item in evidence:
                source = str(item.get("extractor") or "hybrid")
                if source not in ASSIGNMENT_SOURCES:
                    source = "hybrid"
                insert_assignment(
                    db,
                    label_id=label_id,
                    video_id=str(item.get("video_id") or video_id),
                    unit_type="window",
                    status=assignment_status,
                    publish_tier=publish_tier,
                    confidence_score=candidate.confidence_score,
                    evidence=[item],
                    source=source,
                    run_id=run_id,
                    start_ms=_coerce_int(item.get("start_ms")),
                    end_ms=_coerce_int(item.get("end_ms")),
                    window_id=None,
                    chapter_id=None,
                    component_scores={
                        **dict(candidate.component_scores),
                        "source": source,
                    },
                )
                metrics["assignments"] += 1

        finish_extraction_run(db, run_id, "completed", metrics)
        return {"video_id": video_id, "extraction_tier": extraction_tier, "run_id": run_id, **metrics}
    except Exception as exc:
        # SQL errors such as deadlocks leave the current transaction aborted.
        # Roll back before attempting to persist failed-run status. For
        # externally pre-created runs, the run row was already committed by the
        # caller and can be safely updated after rollback. For internally-created
        # runs, rollback may remove the run row; the best-effort update is still
        # harmless and preserves the old API behavior for non-SQL failures.
        try:
            db.rollback()
        except Exception:
            pass
        finish_extraction_run(db, run_id, "failed", metrics, error=str(exc))
        raise


__all__ = [
    "extract_labels_for_video",
]
