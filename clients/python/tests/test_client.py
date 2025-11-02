"""Tests for TranscriptClient."""

from uuid import uuid4

import pytest
from pytest_httpx import HTTPXMock

from transcript_create_client import (
    NotFoundError,
    QuotaExceededError,
    RateLimitError,
    TranscriptClient,
    ValidationError,
)


class TestJobsAPI:
    """Tests for jobs API methods."""

    @pytest.mark.asyncio
    async def test_create_job_success(self, httpx_mock: HTTPXMock, base_url: str) -> None:
        """Test creating a job successfully."""
        job_id = uuid4()
        httpx_mock.add_response(
            method="POST",
            url=f"{base_url}/jobs",
            json={
                "id": str(job_id),
                "kind": "single",
                "state": "pending",
                "error": None,
                "created_at": "2025-01-01T00:00:00Z",
                "updated_at": "2025-01-01T00:00:00Z",
            },
        )

        async with TranscriptClient(base_url=base_url) as client:
            job = await client.create_job(
                url="https://youtube.com/watch?v=test123",
                kind="single",
            )

            assert job.id == job_id
            assert job.kind == "single"
            assert job.state == "pending"

    @pytest.mark.asyncio
    async def test_get_job_success(self, httpx_mock: HTTPXMock, base_url: str) -> None:
        """Test getting a job successfully."""
        job_id = uuid4()
        httpx_mock.add_response(
            method="GET",
            url=f"{base_url}/jobs/{job_id}",
            json={
                "id": str(job_id),
                "kind": "single",
                "state": "completed",
                "error": None,
                "created_at": "2025-01-01T00:00:00Z",
                "updated_at": "2025-01-01T00:00:01Z",
            },
        )

        async with TranscriptClient(base_url=base_url) as client:
            job = await client.get_job(job_id)

            assert job.id == job_id
            assert job.state == "completed"

    @pytest.mark.asyncio
    async def test_get_job_not_found(self, httpx_mock: HTTPXMock, base_url: str) -> None:
        """Test getting a non-existent job."""
        job_id = uuid4()
        httpx_mock.add_response(
            method="GET",
            url=f"{base_url}/jobs/{job_id}",
            status_code=404,
            json={
                "error": "not_found",
                "message": "Job not found",
                "details": {},
            },
        )

        async with TranscriptClient(base_url=base_url) as client:
            with pytest.raises(NotFoundError) as exc_info:
                await client.get_job(job_id)

            assert exc_info.value.status_code == 404


class TestVideosAPI:
    """Tests for videos API methods."""

    @pytest.mark.asyncio
    async def test_get_transcript_success(self, httpx_mock: HTTPXMock, base_url: str) -> None:
        """Test getting a transcript successfully."""
        video_id = uuid4()
        httpx_mock.add_response(
            method="GET",
            url=f"{base_url}/videos/{video_id}/transcript",
            json={
                "video_id": str(video_id),
                "segments": [
                    {
                        "start_ms": 0,
                        "end_ms": 2000,
                        "text": "Hello world",
                        "speaker_label": "Speaker 1",
                    },
                    {
                        "start_ms": 2000,
                        "end_ms": 4000,
                        "text": "This is a test",
                        "speaker_label": "Speaker 1",
                    },
                ],
            },
        )

        async with TranscriptClient(base_url=base_url) as client:
            transcript = await client.get_transcript(video_id)

            assert transcript.video_id == video_id
            assert len(transcript.segments) == 2
            assert transcript.segments[0].text == "Hello world"
            assert transcript.segments[0].speaker_label == "Speaker 1"


class TestSearchAPI:
    """Tests for search API methods."""

    @pytest.mark.asyncio
    async def test_search_success(self, httpx_mock: HTTPXMock, base_url: str) -> None:
        """Test searching successfully."""
        video_id = uuid4()
        httpx_mock.add_response(
            url=f"{base_url}/search?q=query&source=native&limit=50&offset=0",
            json={
                "total": 1,
                "hits": [
                    {
                        "id": 1,
                        "video_id": str(video_id),
                        "start_ms": 1000,
                        "end_ms": 3000,
                        "snippet": "test <em>query</em> match",
                    }
                ],
                "query_time_ms": 10,
            },
        )

        async with TranscriptClient(base_url=base_url) as client:
            results = await client.search(query="query", source="native")

            assert results.total == 1
            assert len(results.hits) == 1
            assert results.hits[0].video_id == video_id
            assert "query" in results.hits[0].snippet


class TestExportAPI:
    """Tests for export API methods."""

    @pytest.mark.asyncio
    async def test_export_srt_success(self, httpx_mock: HTTPXMock, base_url: str) -> None:
        """Test exporting SRT successfully."""
        video_id = uuid4()
        srt_content = b"1\n00:00:00,000 --> 00:00:02,000\nHello world\n"

        httpx_mock.add_response(
            method="GET",
            url=f"{base_url}/videos/{video_id}/transcript.srt",
            content=srt_content,
        )

        async with TranscriptClient(base_url=base_url) as client:
            content = await client.export_srt(video_id)

            assert content == srt_content

    @pytest.mark.asyncio
    async def test_export_pdf_quota_exceeded(self, httpx_mock: HTTPXMock, base_url: str) -> None:
        """Test export with quota exceeded."""
        video_id = uuid4()
        httpx_mock.add_response(
            method="GET",
            url=f"{base_url}/videos/{video_id}/transcript.pdf",
            status_code=402,
            json={
                "error": "quota_exceeded",
                "message": "Export quota exceeded",
                "details": {},
            },
        )

        async with TranscriptClient(base_url=base_url) as client:
            with pytest.raises(QuotaExceededError):
                await client.export_pdf(video_id)


class TestErrorHandling:
    """Tests for error handling."""

    @pytest.mark.asyncio
    async def test_rate_limit_error(self, httpx_mock: HTTPXMock, base_url: str) -> None:
        """Test rate limit error with Retry-After header."""
        httpx_mock.add_response(
            url=f"{base_url}/search?q=test&source=native&limit=50&offset=0",
            status_code=429,
            headers={"Retry-After": "60"},
            json={
                "error": "rate_limit",
                "message": "Rate limit exceeded",
                "details": {},
            },
        )

        async with TranscriptClient(base_url=base_url, max_retries=0) as client:
            with pytest.raises(RateLimitError) as exc_info:
                await client.search(query="test")

            assert exc_info.value.retry_after == 60

    @pytest.mark.asyncio
    async def test_validation_error(self, httpx_mock: HTTPXMock, base_url: str) -> None:
        """Test validation error from API."""
        httpx_mock.add_response(
            method="POST",
            url=f"{base_url}/jobs",
            status_code=422,
            json={
                "error": "validation_error",
                "message": "Invalid URL",
                "details": {"errors": [{"field": "url", "message": "Invalid format"}]},
            },
        )

        async with TranscriptClient(base_url=base_url) as client:
            # Use a URL that passes client-side validation but fails API-side
            with pytest.raises(ValidationError) as exc_info:
                await client.create_job(url="https://example.com/not-youtube", kind="single")

            assert exc_info.value.status_code == 422


class TestRetryLogic:
    """Tests for retry logic."""

    @pytest.mark.asyncio
    async def test_retry_on_server_error(self, httpx_mock: HTTPXMock, base_url: str) -> None:
        """Test retry on server error."""
        video_id = uuid4()

        # First two requests fail with 503
        httpx_mock.add_response(
            method="GET",
            url=f"{base_url}/videos/{video_id}",
            status_code=503,
            json={"error": "service_unavailable", "message": "Service unavailable", "details": {}},
        )
        httpx_mock.add_response(
            method="GET",
            url=f"{base_url}/videos/{video_id}",
            status_code=503,
            json={"error": "service_unavailable", "message": "Service unavailable", "details": {}},
        )

        # Third request succeeds
        httpx_mock.add_response(
            method="GET",
            url=f"{base_url}/videos/{video_id}",
            json={
                "id": str(video_id),
                "youtube_id": "test123",
                "title": "Test Video",
                "duration_seconds": 120,
            },
        )

        async with TranscriptClient(base_url=base_url, max_retries=3) as client:
            video = await client.get_video(video_id)
            assert video.id == video_id


class TestRateLimiting:
    """Tests for rate limiting."""

    @pytest.mark.asyncio
    async def test_rate_limiter(self, httpx_mock: HTTPXMock, base_url: str) -> None:
        """Test rate limiting works."""
        import time

        job_id = uuid4()

        # Mock 5 successful responses
        for _ in range(5):
            httpx_mock.add_response(
                method="GET",
                url=f"{base_url}/jobs/{job_id}",
                json={
                    "id": str(job_id),
                    "kind": "single",
                    "state": "pending",
                    "error": None,
                    "created_at": "2025-01-01T00:00:00Z",
                    "updated_at": "2025-01-01T00:00:00Z",
                },
            )

        # Create client with rate limit of 2 requests per second
        async with TranscriptClient(base_url=base_url, rate_limit=2.0) as client:
            start = time.time()

            # Make 5 requests
            for _ in range(5):
                await client.get_job(job_id)

            elapsed = time.time() - start

            # Should take at least 2 seconds (5 requests / 2 per second = 2.5s)
            # Allow some tolerance for test execution
            assert elapsed >= 1.5
