"""Async HTTP client for Transcript Create API."""

import asyncio
from typing import Any, Dict, Literal, Optional
from uuid import UUID

import httpx

from .exceptions import (
    APIError,
    InvalidAPIKeyError,
    NetworkError,
    NotFoundError,
    QuotaExceededError,
    RateLimitError,
    ServerError,
    TimeoutError,
    TranscriptNotFoundError,
    ValidationError,
)
from .models import (
    CleanedTranscriptResponse,
    FormattedTranscriptResponse,
    Job,
    JobCreate,
    SearchResponse,
    TranscriptResponse,
    VideoInfo,
    YouTubeTranscriptResponse,
)
from .rate_limiter import AdaptiveRateLimiter, RateLimiter
from .retry import RetryConfig, retry_async


class TranscriptClient:
    """Async client for Transcript Create API."""

    def __init__(
        self,
        base_url: str = "http://localhost:8000",
        api_key: Optional[str] = None,
        timeout: float = 30.0,
        max_retries: int = 3,
        rate_limit: Optional[float] = None,
        adaptive_rate_limiting: bool = True,
        retry_config: Optional[RetryConfig] = None,
    ) -> None:
        """Initialize Transcript Create client.

        Args:
            base_url: Base URL of the API
            api_key: API key for authentication (if required)
            timeout: Request timeout in seconds
            max_retries: Maximum number of retries for failed requests
            rate_limit: Maximum requests per second (None for no limit)
            adaptive_rate_limiting: Use adaptive rate limiting
            retry_config: Custom retry configuration
        """
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.timeout = timeout
        self.retry_config = retry_config or RetryConfig(max_retries=max_retries)

        # Setup rate limiting
        if rate_limit is not None:
            if adaptive_rate_limiting:
                self.rate_limiter: Optional[RateLimiter] = AdaptiveRateLimiter(initial_requests_per_second=rate_limit)
            else:
                self.rate_limiter = RateLimiter(requests_per_second=rate_limit)
        else:
            self.rate_limiter = None

        # HTTP client
        self._client: Optional[httpx.AsyncClient] = None

    async def __aenter__(self) -> "TranscriptClient":
        """Async context manager entry."""
        await self._ensure_client()
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """Async context manager exit."""
        await self.close()

    async def _ensure_client(self) -> None:
        """Ensure HTTP client is initialized."""
        if self._client is None:
            headers = {}
            if self.api_key:
                headers["Authorization"] = f"Bearer {self.api_key}"

            self._client = httpx.AsyncClient(
                base_url=self.base_url,
                headers=headers,
                timeout=self.timeout,
                follow_redirects=True,
            )

    async def close(self) -> None:
        """Close HTTP client."""
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    def _handle_error(self, response: httpx.Response) -> None:
        """Handle error responses.

        Args:
            response: HTTP response

        Raises:
            Appropriate exception based on status code
        """
        status_code = response.status_code

        # Try to parse error response
        try:
            error_data = response.json()
            error_code = error_data.get("error", "unknown_error")
            message = error_data.get("message", response.text)
            details = error_data.get("details", {})
        except Exception:
            error_code = "unknown_error"
            message = response.text or f"HTTP {status_code}"
            details = {}

        # Map to specific exceptions
        if status_code == 401:
            raise InvalidAPIKeyError(message, status_code, error_code, details)
        elif status_code == 404:
            if "transcript" in message.lower():
                raise TranscriptNotFoundError(message, status_code, error_code, details)
            raise NotFoundError(message, status_code, error_code, details)
        elif status_code == 402:
            raise QuotaExceededError(message, status_code, error_code, details)
        elif status_code == 422:
            raise ValidationError(message, status_code, error_code, details)
        elif status_code == 429:
            retry_after = None
            if "Retry-After" in response.headers:
                try:
                    retry_after = int(response.headers["Retry-After"])
                except ValueError:
                    pass
            raise RateLimitError(message, retry_after, status_code, error_code, details)
        elif status_code >= 500:
            raise ServerError(message, status_code, error_code, details)
        else:
            raise APIError(message, status_code, error_code, details)

    async def _request(
        self,
        method: str,
        path: str,
        **kwargs: Any,
    ) -> httpx.Response:
        """Make HTTP request with retry logic.

        Args:
            method: HTTP method
            path: API path
            **kwargs: Additional request arguments

        Returns:
            HTTP response

        Raises:
            APIError: On API errors
        """
        await self._ensure_client()
        assert self._client is not None

        # Apply rate limiting
        if self.rate_limiter:
            await self.rate_limiter.acquire()

        async def _do_request() -> httpx.Response:
            try:
                response = await self._client.request(method, path, **kwargs)

                # Handle rate limiting feedback
                if response.status_code == 429 and isinstance(self.rate_limiter, AdaptiveRateLimiter):
                    await self.rate_limiter.on_rate_limit()

                # Check for errors
                if response.status_code >= 400:
                    self._handle_error(response)

                # Success callback for adaptive rate limiting
                if isinstance(self.rate_limiter, AdaptiveRateLimiter):
                    await self.rate_limiter.on_success()

                return response

            except httpx.TimeoutException as e:
                raise TimeoutError(f"Request timeout: {e}") from e
            except httpx.NetworkError as e:
                raise NetworkError(f"Network error: {e}") from e
            except httpx.HTTPStatusError:
                raise

        return await retry_async(_do_request, self.retry_config)

    # Jobs API

    async def create_job(
        self,
        url: str,
        kind: Literal["single", "channel"] = "single",
    ) -> Job:
        """Create a new transcription job.

        Args:
            url: YouTube video or channel URL
            kind: Job type ('single' or 'channel')

        Returns:
            Created job

        Raises:
            ValidationError: Invalid URL or parameters
            APIError: API error
        """
        job_data = JobCreate(url=url, kind=kind)  # type: ignore
        response = await self._request(
            "POST",
            "/jobs",
            json=job_data.model_dump(mode="json"),
        )
        return Job(**response.json())

    async def get_job(self, job_id: UUID) -> Job:
        """Get job status.

        Args:
            job_id: Job ID

        Returns:
            Job information

        Raises:
            NotFoundError: Job not found
            APIError: API error
        """
        response = await self._request("GET", f"/jobs/{job_id}")
        return Job(**response.json())

    async def wait_for_completion(
        self,
        job_id: UUID,
        timeout: float = 3600,
        poll_interval: float = 5.0,
    ) -> Job:
        """Wait for job to complete.

        Args:
            job_id: Job ID
            timeout: Maximum time to wait in seconds
            poll_interval: Polling interval in seconds

        Returns:
            Completed job

        Raises:
            TimeoutError: Job did not complete within timeout
            APIError: API error
        """
        start_time = asyncio.get_event_loop().time()

        while True:
            job = await self.get_job(job_id)

            if job.state in ("completed", "failed"):
                return job

            # Check timeout
            elapsed = asyncio.get_event_loop().time() - start_time
            if elapsed >= timeout:
                raise TimeoutError(f"Job {job_id} did not complete within {timeout} seconds")

            # Wait before next poll
            await asyncio.sleep(poll_interval)

    # Videos API

    async def get_video(self, video_id: UUID) -> VideoInfo:
        """Get video information.

        Args:
            video_id: Video ID

        Returns:
            Video information

        Raises:
            NotFoundError: Video not found
            APIError: API error
        """
        response = await self._request("GET", f"/videos/{video_id}")
        return VideoInfo(**response.json())

    async def get_transcript(
        self,
        video_id: UUID,
        mode: Literal["raw", "cleaned", "formatted"] = "raw",
    ) -> TranscriptResponse | CleanedTranscriptResponse | FormattedTranscriptResponse:
        """Get video transcript.

        Args:
            video_id: Video ID
            mode: Transcript mode - 'raw' (default), 'cleaned', or 'formatted'

        Returns:
            Transcript with segments (type depends on mode)

        Raises:
            TranscriptNotFoundError: Transcript not found
            NotFoundError: Video not found
            APIError: API error
        """
        params = {"mode": mode}
        response = await self._request("GET", f"/videos/{video_id}/transcript", params=params)
        data = response.json()

        if mode == "cleaned":
            return CleanedTranscriptResponse(**data)
        elif mode == "formatted":
            return FormattedTranscriptResponse(**data)
        else:
            return TranscriptResponse(**data)

    async def get_youtube_transcript(self, video_id: UUID) -> YouTubeTranscriptResponse:
        """Get YouTube captions.

        Args:
            video_id: Video ID

        Returns:
            YouTube captions

        Raises:
            NotFoundError: Captions not found
            APIError: API error
        """
        response = await self._request("GET", f"/videos/{video_id}/youtube-transcript.json")
        return YouTubeTranscriptResponse(**response.json())

    # Search API

    async def search(
        self,
        query: str,
        source: Literal["native", "youtube"] = "native",
        video_id: Optional[UUID] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> SearchResponse:
        """Search transcripts.

        Args:
            query: Search query
            source: Search source ('native' or 'youtube')
            video_id: Optional video ID to limit search
            limit: Maximum results to return
            offset: Result offset for pagination

        Returns:
            Search results

        Raises:
            QuotaExceededError: Search quota exceeded
            ValidationError: Invalid parameters
            APIError: API error
        """
        params: Dict[str, Any] = {
            "q": query,
            "source": source,
            "limit": limit,
            "offset": offset,
        }
        if video_id:
            params["video_id"] = str(video_id)

        response = await self._request("GET", "/search", params=params)
        return SearchResponse(**response.json())

    # Export API

    async def export_srt(self, video_id: UUID, source: Literal["native", "youtube"] = "native") -> bytes:
        """Export transcript as SRT.

        Args:
            video_id: Video ID
            source: Export source ('native' or 'youtube')

        Returns:
            SRT file content

        Raises:
            QuotaExceededError: Export quota exceeded
            NotFoundError: Video not found
            APIError: API error
        """
        if source == "native":
            path = f"/videos/{video_id}/transcript.srt"
        else:
            path = f"/videos/{video_id}/youtube-transcript.srt"

        response = await self._request("GET", path)
        return response.content

    async def export_vtt(self, video_id: UUID, source: Literal["native", "youtube"] = "native") -> bytes:
        """Export transcript as VTT.

        Args:
            video_id: Video ID
            source: Export source ('native' or 'youtube')

        Returns:
            VTT file content

        Raises:
            QuotaExceededError: Export quota exceeded
            NotFoundError: Video not found
            APIError: API error
        """
        if source == "native":
            path = f"/videos/{video_id}/transcript.vtt"
        else:
            path = f"/videos/{video_id}/youtube-transcript.vtt"

        response = await self._request("GET", path)
        return response.content

    async def export_pdf(self, video_id: UUID) -> bytes:
        """Export transcript as PDF.

        Args:
            video_id: Video ID

        Returns:
            PDF file content

        Raises:
            QuotaExceededError: Export quota exceeded
            NotFoundError: Video not found
            APIError: API error
        """
        response = await self._request("GET", f"/videos/{video_id}/transcript.pdf")
        return response.content
