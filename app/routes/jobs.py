import uuid

from fastapi import APIRouter, Depends, status

from .. import crud
from ..db import get_db
from ..exceptions import JobNotFoundError
from ..schemas import ErrorResponse, JobCreate, JobStatus

router = APIRouter(prefix="", tags=["Jobs"])


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
        422: {
            "description": "Validation error - invalid URL or parameters",
            "model": ErrorResponse,
        },
    },
)
def create_job(payload: JobCreate, db=Depends(get_db)):
    """Create a new transcription job."""
    job_id = crud.create_job(db, payload.kind, str(payload.url))
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
