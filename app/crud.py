from sqlalchemy import text
import uuid

def create_job(db, kind: str, url: str):
    job_id = uuid.uuid4()
    db.execute(
        text("INSERT INTO jobs (id, kind, input_url) VALUES (:i,:k,:u)"),
        {"i": str(job_id), "k": kind, "u": url}
    )
    db.commit()
    return job_id

def fetch_job(db, job_id):
    row = db.execute(text("SELECT * FROM jobs WHERE id=:i"), {"i": str(job_id)}).mappings().first()
    return row

def list_segments(db, video_id):
    rows = db.execute(
        text("SELECT start_ms,end_ms,text,speaker_label FROM segments WHERE video_id=:v ORDER BY start_ms"),
        {"v": str(video_id)}
    ).all()
    return rows
