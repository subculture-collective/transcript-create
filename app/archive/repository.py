from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.exc import OperationalError, ProgrammingError

from app.schemas import ArchivePopularSearch, ArchiveSummary, VideoInfo


ARCHIVE_VIDEO_FILTER_SQL = """
    EXISTS (SELECT 1 FROM segments s WHERE s.video_id = v.id)
    OR EXISTS (SELECT 1 FROM youtube_transcripts yt WHERE yt.video_id = v.id)
"""


def _video_info_rows_to_models(rows):
    return [VideoInfo(**dict(row)) for row in rows]


class ArchiveRepository:
    def get_summary(self, db, recent_limit: int = 6, popular_limit: int = 8) -> ArchiveSummary:
        try:
            stats = db.execute(
                text(
                    """
                    SELECT
                        video_count,
                        total_duration_seconds,
                        transcript_word_count,
                        archive_updated_at AS updated_at
                    FROM archive_summary_stats
                    WHERE id = 'default'
                    """
                )
            ).mappings().first()
        except (OperationalError, ProgrammingError):
            db.rollback()
            stats = None

        if stats is None:
            stats = db.execute(
                text(
                    f"""
                    SELECT
                        COUNT(*) AS video_count,
                        COALESCE(SUM(COALESCE(v.duration_seconds, 0)), 0) AS total_duration_seconds,
                        0 AS transcript_word_count,
                        MAX(COALESCE(v.updated_at, v.created_at)) AS updated_at
                    FROM videos v
                    WHERE {ARCHIVE_VIDEO_FILTER_SQL}
                    """
                )
            ).mappings().first()

        recent_videos = [
            video
            for video in _video_info_rows_to_models(
                db.execute(
                    text(
                        f"""
                        SELECT
                            v.id, v.youtube_id, v.title, v.duration_seconds, v.state,
                            v.caption_ingest_state, v.diarization_state, v.uploaded_at,
                            v.created_at, v.updated_at, v.channel_name, v.language, v.category,
                            EXISTS (SELECT 1 FROM segments s WHERE s.video_id = v.id) AS has_whisper_transcript,
                            EXISTS (SELECT 1 FROM youtube_transcripts yt WHERE yt.video_id = v.id) AS has_youtube_transcript
                        FROM videos v
                        WHERE ({ARCHIVE_VIDEO_FILTER_SQL})
                        ORDER BY v.uploaded_at DESC NULLS LAST, v.created_at DESC
                        LIMIT :limit
                        """
                    ),
                    {"limit": recent_limit},
                ).mappings().all()
            )
            if video.has_whisper_transcript or video.has_youtube_transcript
        ]

        try:
            popular_rows = (
                db.execute(
                    text(
                        """
                        SELECT term, frequency
                        FROM search_suggestions
                        ORDER BY frequency DESC, last_used DESC
                        LIMIT :limit
                        """
                    ),
                    {"limit": popular_limit},
                )
                .mappings()
                .all()
            )
        except (OperationalError, ProgrammingError):
            db.rollback()
            popular_rows = []

        return ArchiveSummary(
            video_count=int(stats["video_count"] or 0),
            total_duration_seconds=int(stats["total_duration_seconds"] or 0),
            transcript_word_count=int(stats["transcript_word_count"] or 0),
            updated_at=stats["updated_at"],
            recent_videos=recent_videos,
            popular_searches=[ArchivePopularSearch(term=row["term"], frequency=row["frequency"]) for row in popular_rows],
        )

    def refresh_cached_stats(self, db):
        from .refresher import refresh_archive_summary_stats

        return refresh_archive_summary_stats(db)


archive_repository = ArchiveRepository()
