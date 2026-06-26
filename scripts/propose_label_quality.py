#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

from sqlalchemy import text

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from app.archive.labeling.llm_review import review_label_batch_openai_compatible
from app.archive.labeling.quality import assess_label_quality
from app.db import SessionLocal


LABEL_SQL = text(
    """
    SELECT
        l.id::text AS id,
        l.label,
        l.kind,
        l.status,
        l.publish_tier,
        l.confidence_score,
        0::int AS assignments,
        0::int AS distinct_videos,
        '[]'::jsonb AS assignment_sources
    FROM archive_labels AS l
    WHERE l.source = 'automatic'
      AND l.kind = :kind
      AND (:status = '' OR l.status = :status)
      AND (:publish_tier = '' OR l.publish_tier = :publish_tier)
    ORDER BY l.status, l.publish_tier, l.confidence_score DESC, l.label
    LIMIT :limit
    """
)

LABEL_STATS_SQL = text(
    """
    SELECT
        COUNT(a.id)::int AS assignments,
        COUNT(DISTINCT a.video_id)::int AS distinct_videos,
        COALESCE(jsonb_agg(DISTINCT a.source) FILTER (WHERE a.source IS NOT NULL), '[]'::jsonb) AS assignment_sources
    FROM archive_label_assignments AS a
    WHERE a.label_id = :label_id
    """
)

CANONICAL_CONTEXT_SQL = text(
    """
    SELECT label
    FROM archive_labels
    WHERE kind IN ('topic', 'person', 'org', 'place', 'issue')
      AND status = 'published'
      AND canonical_id IS NULL
    ORDER BY confidence_score DESC, label
    LIMIT :limit
    """
)


def _rows(db, args: argparse.Namespace) -> list[dict[str, Any]]:
    rows = [
        dict(row)
        for row in db.execute(
            LABEL_SQL,
            {"kind": args.kind, "status": args.status, "publish_tier": args.publish_tier, "limit": args.limit},
        )
        .mappings()
        .all()
    ]
    if not args.include_stats:
        return rows
    for row in rows:
        stats = db.execute(LABEL_STATS_SQL, {"label_id": row["id"]}).mappings().first()
        if stats:
            row.update(dict(stats))
    return rows


def _canonical_context(db, limit: int) -> list[str]:
    return [str(row[0]) for row in db.execute(CANONICAL_CONTEXT_SQL, {"limit": limit}).all()]


def _primary_source(row: dict[str, Any]) -> str | None:
    sources = row.get("assignment_sources") or []
    if isinstance(sources, str):
        try:
            sources = json.loads(sources)
        except json.JSONDecodeError:
            sources = []
    for preferred in ("alias", "title", "llm", "metadata", "keyphrase"):
        if preferred in sources:
            return preferred
    return str(sources[0]) if sources else None


def _proposal_for_row(row: dict[str, Any]) -> dict[str, Any]:
    assessment = assess_label_quality(
        str(row["label"]),
        source=_primary_source(row),
        assignment_count=int(row.get("assignments") or 0),
        distinct_videos=int(row.get("distinct_videos") or 0),
        existing_canonical=False,
    )
    action = assessment.action
    proposal_type = "deterministic"
    if assessment.canonical_hint and action != "mark_noise":
        action = "alias_to_canonical"
    return {
        "proposal_type": proposal_type,
        "label_id": row["id"],
        "label": row["label"],
        "kind": row["kind"],
        "status": row["status"],
        "publish_tier": row["publish_tier"],
        "assignments": row["assignments"],
        "distinct_videos": row["distinct_videos"],
        "action": action,
        "canonical_label": assessment.canonical_hint,
        "related_labels": [],
        "quality_score": assessment.score,
        "reasons": list(assessment.reasons),
        "needs_llm_review": assessment.needs_llm_review,
    }


def _batch(items: list[dict[str, Any]], max_items: int, max_chars: int) -> list[list[dict[str, Any]]]:
    batches: list[list[dict[str, Any]]] = []
    current: list[dict[str, Any]] = []
    current_chars = 0
    for item in items:
        compact = {
            "label_id": item["label_id"],
            "label": item["label"],
            "kind": item["kind"],
            "current_status": item["status"],
            "current_tier": item["publish_tier"],
            "deterministic_action": item["action"],
            "canonical_hint": item["canonical_label"],
            "reasons": item["reasons"],
        }
        size = len(json.dumps(compact, ensure_ascii=False))
        if current and (len(current) >= max_items or current_chars + size > max_chars):
            batches.append(current)
            current = []
            current_chars = 0
        current.append(compact)
        current_chars += size
    if current:
        batches.append(current)
    return batches


def main() -> None:
    parser = argparse.ArgumentParser(description="Dry-run label quality, alias, and related-label proposals.")
    parser.add_argument("--kind", default="topic")
    parser.add_argument("--status", default="published", help="Filter label status, or empty for all automatic labels.")
    parser.add_argument("--publish-tier", default="", help="Optional publish tier filter.")
    parser.add_argument("--limit", type=int, default=500)
    parser.add_argument("--include-stats", action="store_true", help="Count assignments/videos per label; slower on large DBs.")
    parser.add_argument("--only-action", choices=("", "keep", "review", "mark_noise", "alias_to_canonical"), default="")
    parser.add_argument("--llm", action="store_true", help="Send borderline proposals to an OpenAI-compatible chat/completions endpoint.")
    parser.add_argument("--llm-base-url", default=os.getenv("LABEL_LLM_BASE_URL", os.getenv("OPENAI_BASE_URL", "")))
    parser.add_argument("--llm-api-key", default=os.getenv("LABEL_LLM_API_KEY", os.getenv("OPENAI_API_KEY", "")))
    parser.add_argument("--llm-model", default=os.getenv("LABEL_LLM_MODEL", "gpt-4.1-mini"))
    parser.add_argument("--llm-max-labels-per-request", type=int, default=80)
    parser.add_argument("--llm-max-input-chars", type=int, default=24000)
    parser.add_argument("--canonical-context-limit", type=int, default=300)
    parser.add_argument("--output", default="", help="Optional JSON output path. Prints JSON to stdout when omitted.")
    args = parser.parse_args()

    db = SessionLocal()
    try:
        rows = _rows(db, args)
        proposals = [_proposal_for_row(row) for row in rows]
        if args.only_action:
            proposals = [proposal for proposal in proposals if proposal["action"] == args.only_action]

        llm_batches: list[dict[str, Any]] = []
        if args.llm:
            if not args.llm_base_url:
                raise SystemExit("--llm requires --llm-base-url or LABEL_LLM_BASE_URL/OPENAI_BASE_URL")
            canonical_context = _canonical_context(db, args.canonical_context_limit)
            llm_candidates = [proposal for proposal in proposals if proposal["needs_llm_review"]]
            for index, batch in enumerate(
                _batch(llm_candidates, args.llm_max_labels_per_request, args.llm_max_input_chars), start=1
            ):
                result = review_label_batch_openai_compatible(
                    batch,
                    base_url=args.llm_base_url,
                    api_key=args.llm_api_key,
                    model=args.llm_model,
                    canonical_context=canonical_context,
                )
                llm_batches.append({"batch": index, "input_count": len(batch), "result": result})

        report = {
            "mode": "dry_run_proposals",
            "filters": {"kind": args.kind, "status": args.status, "publish_tier": args.publish_tier, "limit": args.limit},
            "counts": {
                "labels_scanned": len(rows),
                "proposals": len(proposals),
                "mark_noise": sum(1 for proposal in proposals if proposal["action"] == "mark_noise"),
                "alias_to_canonical": sum(1 for proposal in proposals if proposal["action"] == "alias_to_canonical"),
                "review": sum(1 for proposal in proposals if proposal["action"] == "review"),
                "keep": sum(1 for proposal in proposals if proposal["action"] == "keep"),
                "needs_llm_review": sum(1 for proposal in proposals if proposal["needs_llm_review"]),
            },
            "proposals": proposals,
            "llm_batches": llm_batches,
        }
    finally:
        db.close()

    output = json.dumps(report, indent=2, ensure_ascii=False)
    if args.output:
        Path(args.output).write_text(output + "\n")
    else:
        print(output)


if __name__ == "__main__":
    main()
