from __future__ import annotations

import json
from typing import Any

from sqlalchemy import text

from app.archive.labeling.normalization import is_junk_phrase, normalized_alias, slugify_label

ASSIGNMENT_SOURCES = {
    "alias",
    "keyphrase",
    "search",
    "title",
    "embedding_cluster",
    "llm",
    "metadata",
    "admin",
    "hybrid",
}

def _extract_id(row: Any) -> str:
    if row is None:
        raise RuntimeError("expected a returned row")
    if hasattr(row, "_mapping") and "id" in row._mapping:
        return str(row._mapping["id"])
    if isinstance(row, dict) and "id" in row:
        return str(row["id"])
    return str(row[0])


def create_extraction_run(
    db,
    scope: str,
    extraction_tier: str,
    video_id: str | None = None,
    model_name: str | None = None,
) -> str:
    row = db.execute(
        text(
            """
            INSERT INTO archive_extraction_runs (scope, extraction_tier, video_id, model_name, status, started_at)
            VALUES (:scope, :extraction_tier, :video_id, :model_name, 'running', now())
            RETURNING id
            """
        ),
        {
            "scope": scope,
            "extraction_tier": extraction_tier,
            "video_id": video_id,
            "model_name": model_name,
        },
    ).first()
    return _extract_id(row)


def finish_extraction_run(db, run_id: str, status: str, metrics: dict, error: str | None = None) -> None:
    db.execute(
        text(
            """
            UPDATE archive_extraction_runs
            SET status = :status,
                metrics = CAST(:metrics AS jsonb),
                error = :error,
                finished_at = now()
            WHERE id = :run_id
            """
        ),
        {
            "run_id": run_id,
            "status": status,
            "metrics": json.dumps(metrics or {}),
            "error": error,
        },
    )


def upsert_label_candidate(
    db,
    *,
    label: str,
    kind: str,
    aliases: list[str],
    confidence_score: float,
    source: str,
    publish_tier: str,
    status: str,
    run_id: str | None,
) -> str:
    slug = slugify_label(label)
    # Parallel backfills commonly upsert the same automatic label slug from
    # multiple workers. PostgreSQL can deadlock concurrent ON CONFLICT UPDATEs
    # across hot slugs, so serialize each slug within the current transaction.
    db.execute(text("SELECT pg_advisory_xact_lock(hashtext(:slug))"), {"slug": slug})
    row = db.execute(
        text(
            """
            INSERT INTO archive_labels (
                slug, label, kind, status, source, publish_tier,
                confidence_score, created_by_run_id, created_at, updated_at
            )
            VALUES (
                :slug, :label, :kind, :status, :source, :publish_tier,
                :confidence_score, :run_id, now(), now()
            )
            ON CONFLICT (slug) DO UPDATE SET
                label = EXCLUDED.label,
                kind = EXCLUDED.kind,
                confidence_score = GREATEST(archive_labels.confidence_score, EXCLUDED.confidence_score),
                publish_tier = CASE
                    WHEN EXCLUDED.confidence_score >= archive_labels.confidence_score THEN EXCLUDED.publish_tier
                    ELSE archive_labels.publish_tier
                END,
                status = CASE
                    WHEN archive_labels.status IN ('published', 'rejected', 'merged', 'hidden') THEN archive_labels.status
                    ELSE EXCLUDED.status
                END,
                updated_at = now()
            RETURNING id
            """
        ),
        {
            "slug": slug,
            "label": label,
            "kind": kind,
            "status": status,
            "source": source,
            "publish_tier": publish_tier,
            "confidence_score": confidence_score,
            "run_id": run_id,
        },
    ).first()
    label_id = _extract_id(row)

    seen_aliases: set[str] = set()
    for alias in aliases:
        normalized = normalized_alias(alias)
        if not normalized or normalized in seen_aliases or is_junk_phrase(alias):
            continue
        seen_aliases.add(normalized)
        db.execute(
            text(
                """
                INSERT INTO archive_label_aliases (
                    label_id, alias, normalized_alias, source, status, weight, created_at
                )
                VALUES (
                    :label_id, :alias, :normalized_alias, :source, 'active', 1, now()
                )
                ON CONFLICT (label_id, normalized_alias) DO NOTHING
                """
            ),
            {
                "label_id": label_id,
                "alias": alias,
                "normalized_alias": normalized,
                "source": source,
            },
        )

    return label_id


def assignment_key(
    label_id: str,
    video_id: str,
    unit_type: str,
    source: str,
    start_ms: int | None,
    end_ms: int | None,
    window_id: str | None,
    chapter_id: str | None,
) -> str:
    parts = [
        label_id,
        video_id,
        unit_type,
        source,
        "" if start_ms is None else str(start_ms),
        "" if end_ms is None else str(end_ms),
        window_id or "",
        chapter_id or "",
    ]
    return "|".join(parts)


def insert_assignment(
    db,
    *,
    label_id: str,
    video_id: str,
    unit_type: str,
    status: str,
    publish_tier: str,
    confidence_score: float,
    evidence: list[dict],
    source: str,
    run_id: str | None,
    start_ms: int | None = None,
    end_ms: int | None = None,
    window_id: str | None = None,
    chapter_id: str | None = None,
    component_scores: dict[str, Any] | None = None,
) -> str:
    if source not in ASSIGNMENT_SOURCES:
        raise ValueError(f"invalid assignment source: {source!r}")

    key = assignment_key(label_id, video_id, unit_type, source, start_ms, end_ms, window_id, chapter_id)
    db.execute(
        text(
            """
            INSERT INTO archive_label_assignments (
                label_id, video_id, unit_type, chapter_id, window_id, start_ms, end_ms,
                status, publish_tier, confidence_score, evidence_count, evidence,
                source, run_id, assignment_key, component_scores, created_at, updated_at
            ) VALUES (
                :label_id, :video_id, :unit_type, :chapter_id, :window_id, :start_ms, :end_ms,
                :status, :publish_tier, :confidence_score, :evidence_count,
                CAST(:evidence AS jsonb), :source, :run_id, :assignment_key,
                CAST(:component_scores AS jsonb), now(), now()
            )
            ON CONFLICT (assignment_key) DO UPDATE SET
                confidence_score = GREATEST(archive_label_assignments.confidence_score, EXCLUDED.confidence_score),
                evidence = EXCLUDED.evidence,
                evidence_count = EXCLUDED.evidence_count,
                component_scores = EXCLUDED.component_scores,
                publish_tier = CASE
                    WHEN archive_label_assignments.status = 'rejected' THEN archive_label_assignments.publish_tier
                    ELSE EXCLUDED.publish_tier
                END,
                status = CASE
                    WHEN archive_label_assignments.status = 'rejected' THEN 'rejected'
                    ELSE EXCLUDED.status
                END,
                updated_at = now()
            """
        ),
        {
            "label_id": label_id,
            "video_id": video_id,
            "unit_type": unit_type,
            "chapter_id": chapter_id,
            "window_id": window_id,
            "start_ms": start_ms,
            "end_ms": end_ms,
            "status": status,
            "publish_tier": publish_tier,
            "confidence_score": confidence_score,
            "evidence_count": len(evidence),
            "evidence": json.dumps(evidence or []),
            "source": source,
            "run_id": run_id,
            "assignment_key": key,
            "component_scores": json.dumps(component_scores or {}),
        },
    )
    return key


__all__ = [
    "ASSIGNMENT_SOURCES",
    "assignment_key",
    "create_extraction_run",
    "finish_extraction_run",
    "insert_assignment",
    "upsert_label_candidate",
]
