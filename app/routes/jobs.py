import uuid

from fastapi import APIRouter, Depends, HTTPException

from .. import crud
from ..db import get_db
from ..schemas import JobCreate, JobStatus

router = APIRouter()

def _row_to_status(row):
    return JobStatus(
        id=row["id"],
        kind=row["kind"],
        state=row["state"],
        error=row["error"],
        created_at=row["created_at"],
        updated_at=row["updated_at"]
    )

@router.post("/jobs", response_model=JobStatus)
def create_job(payload: JobCreate, db=Depends(get_db)):
    job_id = crud.create_job(db, payload.kind, str(payload.url))
    job = crud.fetch_job(db, job_id)
    return _row_to_status(job)

@router.get("/jobs/{job_id}", response_model=JobStatus)
def get_job(job_id: uuid.UUID, db=Depends(get_db)):
    job = crud.fetch_job(db, job_id)
    if not job:
        raise HTTPException(404)
    return _row_to_status(job)
