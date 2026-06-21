import uuid
from urllib.parse import parse_qs, urlparse

from fastapi import APIRouter, Depends, status
from sqlalchemy import text

from .. import crud
from ..db import get_db
from ..exceptions import DuplicateJobError, JobNotFoundError, RateLimitError, ValidationError
from ..schemas import ErrorResponse, JobCreate, JobStatus
from ..security import ROLE_ADMIN, ROLE_PRO, get_user_required, get_user_role
from ..settings import settings

router = APIRouter(prefix="", tags=["Jobs"])


def _extract_youtube_video_id(url: str) -> str | None:
    """Extract a canonical YouTube video ID for duplicate suppression."""
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    if host == "youtu.be" or host.endswith(".youtu.be"):
        candidate = parsed.path.strip("/").split("/")[0]
        return candidate or None
    if host in {"youtube.com", "www.youtube.com", "m.youtube.com"} or host.endswith(".youtube.com"):
        query_video = parse_qs(parsed.query).get("v", [None])[0]
        if query_video:
            return query_video
    return None


def _normalize_job_url(url: str, kind: str) -> str:
    """Normalize a submitted URL enough for same-owner duplicate detection."""
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    if kind == "single":
        youtube_id = _extract_youtube_video_id(url)
        if youtube_id:
            return f"youtube:video:{youtube_id}"
    if kind == "channel":
        path = parsed.path.rstrip("/")
        if path and not path.endswith("/videos") and ("/channel/" in path or path.startswith("/@")):
            path = f"{path}/videos"
        return f"{parsed.scheme.lower()}://{host}{path}"
    return url.rstrip("/")


def _quota_limits_for_user(user: dict) -> tuple[int, int]:
    """Return (total_limit, channel_limit) for a user in the configured quota window."""
    role = get_user_role(user)
    if role == ROLE_ADMIN and settings.JOB_CREATE_ADMIN_BYPASS_QUOTAS:
        return -1, -1
    if role == ROLE_PRO:
        return settings.JOB_CREATE_PRO_DAILY_LIMIT, settings.JOB_CREATE_PRO_CHANNEL_DAILY_LIMIT
    return settings.JOB_CREATE_DAILY_LIMIT, settings.JOB_CREATE_CHANNEL_DAILY_LIMIT


def _count_recent_user_jobs(db, *, user_id: str, kind: str | None = None) -> int:
    where = ["j.meta->>'owner_user_id' = :user_id", "j.created_at >= now() - make_interval(hours => :hours)"]
    params: dict[str, object] = {
        "user_id": user_id,
        "hours": settings.JOB_CREATE_QUOTA_WINDOW_HOURS,
    }
    if kind:
        where.append("j.kind = :kind")
        params["kind"] = kind
    row = db.execute(
        text(f"SELECT COUNT(*) FROM jobs j WHERE {' AND '.join(where)}"),
        params,
    ).first()
    return int(row[0] if row else 0)


def _enforce_job_quota(db, *, user: dict, kind: str) -> None:
    user_id = str(user["id"])
    total_limit, channel_limit = _quota_limits_for_user(user)
    window_hours = settings.JOB_CREATE_QUOTA_WINDOW_HOURS

    if total_limit >= 0 and _count_recent_user_jobs(db, user_id=user_id) >= total_limit:
        raise RateLimitError(
            "Job creation quota exceeded. Please try again later.",
            details={
                "limit": total_limit,
                "window_hours": window_hours,
                "quota": "jobs",
            },
        )
    if kind == "channel" and channel_limit >= 0 and _count_recent_user_jobs(db, user_id=user_id, kind="channel") >= channel_limit:
        raise RateLimitError(
            "Channel job creation quota exceeded. Please try again later.",
            details={
                "limit": channel_limit,
                "window_hours": window_hours,
                "quota": "channel_jobs",
            },
        )


def _find_duplicate_job(db, *, user_id: str, kind: str, normalized_url: str, youtube_id: str | None):
    params = {
        "user_id": user_id,
        "kind": kind,
        "normalized_url": normalized_url,
        "youtube_id": youtube_id,
    }
    return (
        db.execute(
            text(
                """
                SELECT j.id
                FROM jobs j
                LEFT JOIN videos v ON v.job_id = j.id
                WHERE j.meta->>'owner_user_id' = :user_id
                  AND j.kind = :kind
                  AND j.state <> 'failed'
                  AND (
                    j.meta->>'normalized_url' = :normalized_url
                    OR (:youtube_id IS NOT NULL AND (j.meta->>'youtube_id' = :youtube_id OR v.youtube_id = :youtube_id))
                  )
                ORDER BY j.created_at DESC
                LIMIT 1
                """
            ),
            params,
        )
        .mappings()
        .first()
    )


def _enforce_job_shape_limits(payload: JobCreate) -> None:
    if payload.kind == "channel" and settings.JOB_CREATE_MAX_CHANNEL_VIDEOS <= 0:
        raise ValidationError("Channel job creation is disabled", field="kind")
    if (
        payload.batch_expected_jobs is not None
        and payload.batch_expected_jobs > settings.JOB_CREATE_MAX_BATCH_EXPECTED_JOBS
    ):
        raise ValidationError(
            f"batch_expected_jobs cannot exceed {settings.JOB_CREATE_MAX_BATCH_EXPECTED_JOBS}",
            field="batch_expected_jobs",
            details={"max": settings.JOB_CREATE_MAX_BATCH_EXPECTED_JOBS},
        )


def _row_to_status(row):
    return JobStatus(
        id=row["id"],
        kind=row["kind"],
        state=row["state"],
        error=row["error"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


@router.post(
    "/jobs",
    response_model=JobStatus,
    status_code=status.HTTP_200_OK,
    summary="Create a transcription job",
    description="""
    Create a new transcription job for a YouTube video or channel.

    Authentication is required via session cookie or API key. Creation is subject
    to configurable per-user quotas and channel-size caps to protect GPU, disk,
    and YouTube quota.

    The job will be processed asynchronously by the worker. Use the returned job ID
    to check status via GET /jobs/{job_id}.

    **Job Types:**
    - `single`: Transcribe one video
    - `channel`: Transcribe all videos from a channel (may create many video jobs)

    **Job States:**
    - `pending`: Job created, waiting to be expanded
    - `expanded`: Videos identified and queued for transcription
    - `completed`: All videos transcribed successfully
    - `failed`: Job encountered an error

    **Quality Settings:**
    Optionally specify quality settings for transcription:
    - `preset`: 'fast', 'balanced', or 'accurate'
    - `language`: Language code (e.g., 'en', 'es') or omit for auto-detection
    - `model`: Whisper model size (overrides preset)
    - `beam_size`: Beam search size (1-10)
    - `temperature`: Sampling temperature (0.0-1.0)
    - `word_timestamps`: Extract word-level timestamps (default: true)
    """,
    responses={
        200: {
            "description": "Job created successfully",
            "content": {
                "application/json": {
                    "example": {
                        "id": "123e4567-e89b-12d3-a456-426614174000",
                        "kind": "single",
                        "state": "pending",
                        "error": None,
                        "created_at": "2025-10-25T10:30:00Z",
                        "updated_at": "2025-10-25T10:30:00Z",
                    }
                }
            },
        },
        401: {
            "description": "Authentication required",
            "model": ErrorResponse,
        },
        409: {
            "description": "Duplicate active job",
            "model": ErrorResponse,
        },
        429: {
            "description": "Job creation quota exceeded",
            "model": ErrorResponse,
        },
        422: {
            "description": "Validation error - invalid URL or parameters",
            "model": ErrorResponse,
        },
    },
)
def create_job(payload: JobCreate, db=Depends(get_db), user=Depends(get_user_required)):
    """Create a new transcription job."""
    _enforce_job_shape_limits(payload)
    _enforce_job_quota(db, user=user, kind=payload.kind)

    owner_user_id = str(user["id"])
    source_url = str(payload.url)
    normalized_url = _normalize_job_url(source_url, payload.kind)
    youtube_id = _extract_youtube_video_id(source_url) if payload.kind == "single" else None

    duplicate = _find_duplicate_job(
        db,
        user_id=owner_user_id,
        kind=payload.kind,
        normalized_url=normalized_url,
        youtube_id=youtube_id,
    )
    if duplicate:
        raise DuplicateJobError(
            source_url,
            existing_job_id=str(duplicate["id"]),
            details={
                "url": source_url,
                "normalized_url": normalized_url,
                "youtube_id": youtube_id,
                "existing_job_id": str(duplicate["id"]),
            },
        )

    # Build job metadata with quality settings and vocabulary
    meta: dict[str, object] = {
        "owner_user_id": owner_user_id,
        "created_by": "api_key" if user.get("api_key_id") else "session",
        "normalized_url": normalized_url,
    }
    if user.get("api_key_id"):
        meta["api_key_id"] = str(user["api_key_id"])
    if youtube_id:
        meta["youtube_id"] = youtube_id
    if payload.kind == "channel":
        meta["max_channel_videos"] = settings.JOB_CREATE_MAX_CHANNEL_VIDEOS
    if payload.quality:
        meta["quality"] = payload.quality.model_dump(exclude_none=True)
    if payload.vocabulary_ids:
        meta["vocabulary_ids"] = [str(vid) for vid in payload.vocabulary_ids]
    if payload.batch_id:
        meta["batch_id"] = payload.batch_id
    if payload.batch_expected_jobs:
        meta["batch_expected_jobs"] = payload.batch_expected_jobs
    if payload.staged:
        meta["staged"] = True

    job_id = crud.create_job(db, payload.kind, str(payload.url), meta=meta)
    job = crud.fetch_job(db, job_id)
    return _row_to_status(job)


@router.get(
    "/jobs/{job_id}",
    response_model=JobStatus,
    summary="Get job status",
    description="""
    Retrieve the current status of a transcription job.

    Poll this endpoint to monitor job progress. Check the `state` field to determine
    if the job is still processing or has completed.
    """,
    responses={
        200: {
            "description": "Job status retrieved successfully",
        },
        404: {
            "description": "Job not found",
            "model": ErrorResponse,
            "content": {
                "application/json": {
                    "example": {
                        "error": "job_not_found",
                        "message": "Job with ID 123e4567-e89b-12d3-a456-426614174000 not found",
                        "details": {},
                    }
                }
            },
        },
    },
)
def get_job(job_id: uuid.UUID, db=Depends(get_db)):
    """Get the status of a specific job."""
    job = crud.fetch_job(db, job_id)
    if not job:
        raise JobNotFoundError(str(job_id))
    return _row_to_status(job)
