from __future__ import annotations

from sqlalchemy import text

from app.schemas import ArchiveSummaryStats

from .repository import ARCHIVE_VIDEO_FILTER_SQL


def refresh_archive_summary_stats(db) -> ArchiveSummaryStats:
    stats = db.execute(
        text(
            f"""
            SELECT
                COUNT(*) AS video_count,
                COALESCE(SUM(COALESCE(v.duration_seconds, 0)), 0) AS total_duration_seconds,
                MAX(COALESCE(v.updated_at, v.created_at)) AS archive_updated_at
            FROM videos v
            WHERE {ARCHIVE_VIDEO_FILTER_SQL}
            """
        )
    ).mappings().one()

    native_words = db.execute(
        text(
            f"""
            SELECT COALESCE(SUM(
                CASE
                    WHEN btrim(COALESCE(t.full_text, '')) = '' THEN 0
                    ELSE cardinality(regexp_split_to_array(btrim(t.full_text), '\\s+'))
                END
            ), 0)
            FROM transcripts t
            JOIN videos v ON v.id = t.video_id
            WHERE {ARCHIVE_VIDEO_FILTER_SQL}
            """
        )
    ).scalar_one()

    youtube_words = db.execute(
        text(
            f"""
            SELECT COALESCE(SUM(
                CASE
                    WHEN btrim(COALESCE(yt.full_text, '')) = '' THEN 0
                    ELSE cardinality(regexp_split_to_array(btrim(yt.full_text), '\\s+'))
                END
            ), 0)
            FROM youtube_transcripts yt
            JOIN videos v ON v.id = yt.video_id
            WHERE {ARCHIVE_VIDEO_FILTER_SQL}
            """
        )
    ).scalar_one()

    db.execute(
        text(
            """
            INSERT INTO archive_summary_stats (
                id,
                video_count,
                total_duration_seconds,
                transcript_word_count,
                archive_updated_at,
                calculated_at
            ) VALUES (
                'default', :video_count, :total_duration_seconds,
                :transcript_word_count, :archive_updated_at, now()
            )
            ON CONFLICT (id) DO UPDATE SET
                video_count = EXCLUDED.video_count,
                total_duration_seconds = EXCLUDED.total_duration_seconds,
                transcript_word_count = EXCLUDED.transcript_word_count,
                archive_updated_at = EXCLUDED.archive_updated_at,
                calculated_at = now()
            """
        ),
        {
            "video_count": int(stats["video_count"] or 0),
            "total_duration_seconds": int(stats["total_duration_seconds"] or 0),
            "transcript_word_count": int((native_words or 0) + (youtube_words or 0)),
            "archive_updated_at": stats["archive_updated_at"],
        },
    )

    return ArchiveSummaryStats(
        video_count=int(stats["video_count"] or 0),
        total_duration_seconds=int(stats["total_duration_seconds"] or 0),
        transcript_word_count=int((native_words or 0) + (youtube_words or 0)),
        archive_updated_at=stats["archive_updated_at"],
    )
