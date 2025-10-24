"""Integration tests for export functionality (SRT, PDF, etc.)."""

import re
import uuid
from io import BytesIO

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

try:
    from PyPDF2 import PdfReader
except ImportError:
    PdfReader = None


class TestExportSRT:
    """Integration tests for SRT export."""

    @pytest.mark.timeout(60)
    def test_export_srt_not_found(self, integration_client: TestClient, clean_test_data):
        """Test exporting SRT for non-existent video."""
        fake_video_id = str(uuid.uuid4())
        response = integration_client.get(f"/videos/{fake_video_id}/transcript.srt")
        assert response.status_code == 404

    @pytest.mark.timeout(60)
    def test_export_srt_with_segments(
        self, integration_client: TestClient, integration_db, clean_test_data, sample_transcript_segments
    ):
        """Test exporting SRT format with segments."""
        # Create job, video, transcript, and segments
        job_id = uuid.uuid4()
        video_id = uuid.uuid4()
        transcript_id = uuid.uuid4()

        integration_db.execute(
            text(
                """
                INSERT INTO jobs (id, kind, state, input_url)
                VALUES (:job_id, 'single', 'completed', 'https://youtube.com/watch?v=test')
            """
            ),
            {"job_id": str(job_id)},
        )

        integration_db.execute(
            text(
                """
                INSERT INTO videos (id, job_id, youtube_id, idx, title, duration_seconds, state)
                VALUES (:video_id, :job_id, 'test123', 0, 'Test Video', 180, 'completed')
            """
            ),
            {"video_id": str(video_id), "job_id": str(job_id)},
        )

        integration_db.execute(
            text(
                """
                INSERT INTO transcripts (id, video_id, model, language)
                VALUES (:transcript_id, :video_id, 'test-model', 'en')
            """
            ),
            {"transcript_id": str(transcript_id), "video_id": str(video_id)},
        )

        # Insert segments
        for i, seg in enumerate(sample_transcript_segments):
            integration_db.execute(
                text(
                    """
                    INSERT INTO segments (transcript_id, idx, start_ms, end_ms, text, speaker_label)
                    VALUES (:transcript_id, :idx, :start_ms, :end_ms, :text, :speaker_label)
                """
                ),
                {
                    "transcript_id": str(transcript_id),
                    "idx": i,
                    "start_ms": seg["start_ms"],
                    "end_ms": seg["end_ms"],
                    "text": seg["text"],
                    "speaker_label": seg.get("speaker_label"),
                },
            )

        integration_db.commit()

        # Export SRT
        response = integration_client.get(f"/videos/{video_id}/transcript.srt")
        assert response.status_code == 200
        assert response.headers["content-type"] == "text/plain; charset=utf-8"

        # Verify SRT format
        srt_content = response.text

        # Check for basic SRT structure
        # SRT format: sequence number, timestamps, text, blank line
        assert "1\n" in srt_content or srt_content.startswith("1\n")
        assert "-->" in srt_content

        # Check that segment text appears
        for seg in sample_transcript_segments:
            assert seg["text"] in srt_content

    @pytest.mark.timeout(60)
    def test_srt_timestamp_format(
        self, integration_client: TestClient, integration_db, clean_test_data, sample_transcript_segments
    ):
        """Test that SRT timestamps are in correct format."""
        # Create test data
        job_id = uuid.uuid4()
        video_id = uuid.uuid4()
        transcript_id = uuid.uuid4()

        integration_db.execute(
            text(
                """
                INSERT INTO jobs (id, kind, state, input_url)
                VALUES (:job_id, 'single', 'completed', 'https://youtube.com/watch?v=test')
            """
            ),
            {"job_id": str(job_id)},
        )

        integration_db.execute(
            text(
                """
                INSERT INTO videos (id, job_id, youtube_id, idx, title, duration_seconds, state)
                VALUES (:video_id, :job_id, 'test123', 0, 'Test Video', 180, 'completed')
            """
            ),
            {"video_id": str(video_id), "job_id": str(job_id)},
        )

        integration_db.execute(
            text(
                """
                INSERT INTO transcripts (id, video_id, model, language)
                VALUES (:transcript_id, :video_id, 'test-model', 'en')
            """
            ),
            {"transcript_id": str(transcript_id), "video_id": str(video_id)},
        )

        integration_db.execute(
            text(
                """
                INSERT INTO segments (transcript_id, idx, start_ms, end_ms, text)
                VALUES (:transcript_id, 0, 0, 1500, 'Test text')
            """
            ),
            {"transcript_id": str(transcript_id)},
        )

        integration_db.commit()

        # Export SRT
        response = integration_client.get(f"/videos/{video_id}/transcript.srt")
        if response.status_code == 200:
            srt_content = response.text

            # SRT timestamp format: HH:MM:SS,mmm --> HH:MM:SS,mmm
            timestamp_pattern = r"\d{2}:\d{2}:\d{2},\d{3} --> \d{2}:\d{2}:\d{2},\d{3}"
            matches = re.findall(timestamp_pattern, srt_content)
            assert len(matches) > 0


class TestExportPDF:
    """Integration tests for PDF export."""

    @pytest.mark.timeout(60)
    def test_export_pdf_not_found(self, integration_client: TestClient, clean_test_data):
        """Test exporting PDF for non-existent video."""
        fake_video_id = str(uuid.uuid4())
        response = integration_client.get(f"/videos/{fake_video_id}/transcript.pdf")
        assert response.status_code == 404

    @pytest.mark.timeout(60)
    @pytest.mark.skipif(PdfReader is None, reason="PyPDF2 not installed")
    def test_export_pdf_with_segments(
        self, integration_client: TestClient, integration_db, clean_test_data, sample_transcript_segments
    ):
        """Test exporting PDF format with segments."""
        # Create job, video, transcript, and segments
        job_id = uuid.uuid4()
        video_id = uuid.uuid4()
        transcript_id = uuid.uuid4()

        integration_db.execute(
            text(
                """
                INSERT INTO jobs (id, kind, state, input_url)
                VALUES (:job_id, 'single', 'completed', 'https://youtube.com/watch?v=test')
            """
            ),
            {"job_id": str(job_id)},
        )

        integration_db.execute(
            text(
                """
                INSERT INTO videos (id, job_id, youtube_id, idx, title, duration_seconds, state)
                VALUES (:video_id, :job_id, 'test123', 0, 'Test Video', 180, 'completed')
            """
            ),
            {"video_id": str(video_id), "job_id": str(job_id)},
        )

        integration_db.execute(
            text(
                """
                INSERT INTO transcripts (id, video_id, model, language)
                VALUES (:transcript_id, :video_id, 'test-model', 'en')
            """
            ),
            {"transcript_id": str(transcript_id), "video_id": str(video_id)},
        )

        # Insert segments
        for i, seg in enumerate(sample_transcript_segments):
            integration_db.execute(
                text(
                    """
                    INSERT INTO segments (transcript_id, idx, start_ms, end_ms, text, speaker_label)
                    VALUES (:transcript_id, :idx, :start_ms, :end_ms, :text, :speaker_label)
                """
                ),
                {
                    "transcript_id": str(transcript_id),
                    "idx": i,
                    "start_ms": seg["start_ms"],
                    "end_ms": seg["end_ms"],
                    "text": seg["text"],
                    "speaker_label": seg.get("speaker_label"),
                },
            )

        integration_db.commit()

        # Export PDF
        response = integration_client.get(f"/videos/{video_id}/transcript.pdf")
        assert response.status_code == 200
        assert response.headers["content-type"] == "application/pdf"

        # Verify PDF is valid
        pdf_content = BytesIO(response.content)
        reader = PdfReader(pdf_content)

        # Check that PDF has at least one page
        assert len(reader.pages) > 0

        # Extract text and verify segment content appears
        text_content = ""
        for page in reader.pages:
            text_content += page.extract_text()

        # Check that segment text appears in PDF
        for seg in sample_transcript_segments:
            assert seg["text"] in text_content


class TestExportFormats:
    """Tests for various export format edge cases."""

    @pytest.mark.timeout(60)
    def test_export_empty_transcript(self, integration_client: TestClient, integration_db, clean_test_data):
        """Test exporting when transcript has no segments."""
        # Create job, video, and transcript but no segments
        job_id = uuid.uuid4()
        video_id = uuid.uuid4()
        transcript_id = uuid.uuid4()

        integration_db.execute(
            text(
                """
                INSERT INTO jobs (id, kind, state, input_url)
                VALUES (:job_id, 'single', 'completed', 'https://youtube.com/watch?v=test')
            """
            ),
            {"job_id": str(job_id)},
        )

        integration_db.execute(
            text(
                """
                INSERT INTO videos (id, job_id, youtube_id, idx, title, duration_seconds, state)
                VALUES (:video_id, :job_id, 'test123', 0, 'Test Video', 180, 'completed')
            """
            ),
            {"video_id": str(video_id), "job_id": str(job_id)},
        )

        integration_db.execute(
            text(
                """
                INSERT INTO transcripts (id, video_id, model, language)
                VALUES (:transcript_id, :video_id, 'test-model', 'en')
            """
            ),
            {"transcript_id": str(transcript_id), "video_id": str(video_id)},
        )

        integration_db.commit()

        # Try to export (should handle empty gracefully)
        response = integration_client.get(f"/videos/{video_id}/transcript.srt")
        # Might return 200 with empty content or 404
        assert response.status_code in [200, 404]
