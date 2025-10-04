import logging, os
from fastapi import FastAPI, Depends, HTTPException
from .db import get_db
from . import crud
from .schemas import JobCreate, JobStatus, TranscriptResponse, Segment
import uuid

logging.basicConfig(
    level=getattr(logging, (os.environ.get("LOG_LEVEL") or "INFO").upper(), logging.INFO),
    format='%(asctime)s %(levelname)s [api] %(message)s',
)
app = FastAPI()

@app.post("/jobs", response_model=JobStatus)
def create_job(payload: JobCreate, db=Depends(get_db)):
    job_id = crud.create_job(db, payload.kind, str(payload.url))
    job = crud.fetch_job(db, job_id)
    return _row_to_status(job)

@app.get("/jobs/{job_id}", response_model=JobStatus)
def get_job(job_id: uuid.UUID, db=Depends(get_db)):
    job = crud.fetch_job(db, job_id)
    if not job:
        raise HTTPException(404)
    return _row_to_status(job)

@app.get("/videos/{video_id}/transcript", response_model=TranscriptResponse)
def get_transcript(video_id: uuid.UUID, db=Depends(get_db)):
    segs = crud.list_segments(db, video_id)
    if not segs:
        raise HTTPException(404, "No segments")
    return TranscriptResponse(
        video_id=video_id,
        segments=[Segment(start_ms=r[0], end_ms=r[1], text=r[2], speaker_label=r[3]) for r in segs]
    )

def _row_to_status(row):
    return JobStatus(
        id=row["id"],
        kind=row["kind"],
        state=row["state"],
        error=row["error"],
        created_at=row["created_at"],
        updated_at=row["updated_at"]
    )
