from __future__ import annotations

from sqlalchemy import text


class VideoRepository:
    def __init__(self, conn):
        self.conn = conn

    def mark_completed(self, video_id: str, *, diarization_state: str) -> None:
        self.conn.execute(
            text(
                """
                UPDATE videos
                SET state='completed', error=NULL, diarization_state=:diarization_state, updated_at=now()
                WHERE id=:video_id
                """
            ),
            {"video_id": video_id, "diarization_state": diarization_state},
        )

    def mark_caption_running(self, video_id: str) -> None:
        self.conn.execute(
            text(
                """
                UPDATE videos
                SET caption_ingest_state='running', caption_ingest_error=NULL, updated_at=now()
                WHERE id=:video_id
                """
            ),
            {"video_id": video_id},
        )

    def mark_caption_pending_with_error(self, video_id: str, error: str) -> None:
        self.conn.execute(
            text(
                """
                UPDATE videos
                SET caption_ingest_state='pending', caption_ingest_error=:error, updated_at=now()
                WHERE id=:video_id
                """
            ),
            {"video_id": video_id, "error": error[:5000]},
        )

    def mark_caption_failed(self, video_id: str, error: str) -> None:
        self.conn.execute(
            text(
                """
                UPDATE videos
                SET caption_ingest_state='failed', caption_ingest_error=:error, updated_at=now()
                WHERE id=:video_id
                """
            ),
            {"video_id": video_id, "error": error[:5000]},
        )

    def mark_caption_unavailable(self, video_id: str) -> None:
        self.conn.execute(
            text(
                """
                UPDATE videos
                SET caption_ingest_state='unavailable', caption_ingest_error=NULL, updated_at=now()
                WHERE id=:video_id
                """
            ),
            {"video_id": video_id},
        )

    def mark_caption_completed(self, video_id: str) -> None:
        self.conn.execute(
            text(
                """
                UPDATE videos
                SET caption_ingest_state='completed', caption_ingest_error=NULL, updated_at=now()
                WHERE id=:video_id
                """
            ),
            {"video_id": video_id},
        )
