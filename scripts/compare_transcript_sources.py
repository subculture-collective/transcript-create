#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from app.transcripts.comparison import compare_sources, render_markdown_report


def _load_candidates(conn, limit: int):
    from sqlalchemy import text

    return conn.execute(
        text(
            """
            SELECT v.id, v.youtube_id, v.title
            FROM videos v
            WHERE EXISTS (SELECT 1 FROM segments s WHERE s.video_id = v.id)
              AND EXISTS (SELECT 1 FROM youtube_transcripts yt WHERE yt.video_id = v.id)
            ORDER BY COALESCE(v.uploaded_at, v.created_at) DESC, v.created_at DESC
            LIMIT :limit
            """
        ),
        {"limit": limit},
    ).mappings().all()


def _load_whisper_segments(conn, video_id):
    from app import crud
    from app.transcripts.types import TranscriptSegment

    rows = crud.list_segments(conn, video_id)
    return [
        TranscriptSegment(
            start_ms=int(r.start_ms),
            end_ms=int(r.end_ms),
            text=str(r.text or ""),
            speaker_label=getattr(r, "speaker_label", None),
        )
        for r in rows
    ]


def _load_youtube_segments(conn, video_id):
    from app import crud
    from app.transcripts.youtube_formatting import youtube_rows_to_segments

    yt = crud.get_youtube_transcript(conn, video_id)
    if not yt:
        return []
    rows = crud.list_youtube_segments(conn, yt["id"])
    return youtube_rows_to_segments([(r.start_ms, r.end_ms, r.text) for r in rows])


def main(limit: int = 100, bucket_ms: int = 10000, output_dir: str = "reports", json_output: str | None = None, markdown_output: str | None = None) -> int:
    from sqlalchemy import create_engine
    from app.settings import settings

    engine = create_engine(settings.DATABASE_URL, pool_pre_ping=True)
    with engine.begin() as conn:
        candidates = _load_candidates(conn, limit)
        videos = []
        recommendation_counts: Counter[str] = Counter()
        for row in candidates:
            whisper = _load_whisper_segments(conn, row["id"])
            youtube = _load_youtube_segments(conn, row["id"])
            result = compare_sources(str(row["id"]), whisper, youtube, bucket_ms=bucket_ms)
            videos.append(
                {
                    "video_id": str(row["id"]),
                    "youtube_id": row["youtube_id"],
                    "title": row["title"],
                    "recommendation": result["recommendation"],
                    "metrics": result,
                }
            )
            recommendation_counts[result["recommendation"]] += 1

    video_count = len(videos)
    report = {
        "summary": {
            "video_count": video_count,
            "recommendations": dict(recommendation_counts),
            "bucket_ms": bucket_ms,
            "average_whisper_coverage": sum(v["metrics"]["whisper"]["coverage_ratio"] for v in videos) / video_count if video_count else 0.0,
            "average_youtube_coverage": sum(v["metrics"]["youtube"]["coverage_ratio"] for v in videos) / video_count if video_count else 0.0,
            "average_similarity": sum(v["metrics"]["whisper"]["average_similarity"] for v in videos) / video_count if video_count else 0.0,
        },
        "videos": videos,
    }
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    outdir = Path(output_dir)
    outdir.mkdir(parents=True, exist_ok=True)
    json_path = Path(json_output) if json_output else outdir / f"transcript-source-comparison-{stamp}.json"
    md_path = Path(markdown_output) if markdown_output else outdir / f"transcript-source-comparison-{stamp}.md"
    json_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    md_path.write_text(render_markdown_report(report), encoding="utf-8")
    print(json_path)
    print(md_path)
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Compare Whisper transcripts against YouTube captions")
    parser.add_argument("--limit", type=int, default=100)
    parser.add_argument("--bucket-ms", type=int, default=10000)
    parser.add_argument("--output-dir", default="reports")
    parser.add_argument("--json-output")
    parser.add_argument("--markdown-output")
    args = parser.parse_args()
    raise SystemExit(main(limit=args.limit, bucket_ms=args.bucket_ms, output_dir=args.output_dir, json_output=args.json_output, markdown_output=args.markdown_output))
