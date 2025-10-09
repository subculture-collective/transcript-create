import logging, os
from typing import Optional
from fastapi import FastAPI, Depends, HTTPException, Response
from .db import get_db
from .settings import settings
import requests
from . import crud
from .schemas import JobCreate, JobStatus, TranscriptResponse, Segment, YouTubeTranscriptResponse, YTSegment, SearchResponse, SearchHit
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

@app.get("/videos/{video_id}/youtube-transcript", response_model=YouTubeTranscriptResponse)
def get_youtube_transcript(video_id: uuid.UUID, db=Depends(get_db)):
    yt = crud.get_youtube_transcript(db, video_id)
    if not yt:
        raise HTTPException(404, "No YouTube transcript")
    segs = crud.list_youtube_segments(db, yt["id"])
    return YouTubeTranscriptResponse(
        video_id=video_id,
        language=yt.get("language"),
        kind=yt.get("kind"),
        full_text=yt.get("full_text"),
        segments=[YTSegment(start_ms=r[0], end_ms=r[1], text=r[2]) for r in segs],
    )

def _fmt_time_ms(ms: int) -> str:
    s, ms = divmod(ms, 1000)
    h, s = divmod(s, 3600)
    m, s = divmod(s, 60)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"

@app.get("/videos/{video_id}/youtube-transcript.srt")
def get_youtube_transcript_srt(video_id: uuid.UUID, db=Depends(get_db)):
    yt = crud.get_youtube_transcript(db, video_id)
    if not yt:
        raise HTTPException(404, "No YouTube transcript")
    segs = crud.list_youtube_segments(db, yt["id"])
    lines = []
    for i, (start_ms, end_ms, text) in enumerate(segs, start=1):
        lines.append(str(i))
        lines.append(f"{_fmt_time_ms(start_ms)} --> {_fmt_time_ms(end_ms)}")
        lines.append(text)
        lines.append("")
    body = "\n".join(lines)
    return Response(content=body, media_type="text/plain")

@app.get("/videos/{video_id}/youtube-transcript.vtt")
def get_youtube_transcript_vtt(video_id: uuid.UUID, db=Depends(get_db)):
    yt = crud.get_youtube_transcript(db, video_id)
    if not yt:
        raise HTTPException(404, "No YouTube transcript")
    segs = crud.list_youtube_segments(db, yt["id"])
    def vtt_time(ms: int) -> str:
        s, ms = divmod(ms, 1000)
        h, s = divmod(s, 3600)
        m, s = divmod(s, 60)
        # VTT uses dot for milliseconds and can omit hours if 0, but we keep HH:MM:SS.mmm
        return f"{h:02d}:{m:02d}:{s:02d}.{ms:03d}"
    lines = ["WEBVTT", ""]
    for (start_ms, end_ms, text) in segs:
        lines.append(f"{vtt_time(start_ms)} --> {vtt_time(end_ms)}")
        lines.append(text)
        lines.append("")
    body = "\n".join(lines)
    return Response(content=body, media_type="text/vtt")

@app.get("/search", response_model=SearchResponse)
def search(q: str, source: str = "native", video_id: Optional[uuid.UUID] = None, limit: int = 50, offset: int = 0, db=Depends(get_db)):
    if not q or not q.strip():
        raise HTTPException(400, "Missing query parameter 'q'")
    if source not in ("native", "youtube"):
        raise HTTPException(400, "Invalid source. Use 'native' or 'youtube'")
    if limit < 1 or limit > 200:
        raise HTTPException(400, "limit must be between 1 and 200")
    if settings.SEARCH_BACKEND == "opensearch":
        # OpenSearch path: query the selected index with a simple match query and return hits
        index = settings.OPENSEARCH_INDEX_NATIVE if source == "native" else settings.OPENSEARCH_INDEX_YOUTUBE
        query = {
            "from": offset,
            "size": limit,
            "query": {
                "bool": {
                    "should": [
                        {"multi_match": {"query": q, "type": "phrase", "fields": ["text^3", "text.shingle^4"]}},
                        {"multi_match": {"query": q, "fields": ["text^2", "text.ngram^0.5", "text.edge^1.5"]}},
                        {"prefix": {"text.edge": {"value": q.lower(), "boost": 1.2}}}
                    ],
                    "minimum_should_match": 1
                }
            },
            "highlight": {
                "fields": {"text": {"number_of_fragments": 3, "fragment_size": 180}}
            }
        }
        if video_id:
            query["query"]["bool"].setdefault("filter", []).append({"term": {"video_id": str(video_id)}})
        try:
            r = requests.post(f"{settings.OPENSEARCH_URL}/{index}/_search", json=query, timeout=10)
            r.raise_for_status()
            data = r.json()
        except Exception as e:
            raise HTTPException(500, f"OpenSearch query failed: {e}")
        hits = []
        for h in data.get("hits", {}).get("hits", []):
            src = h.get("_source", {})
            hl = h.get("highlight", {}).get("text", [src.get("text", "")])
            hits.append(SearchHit(
                id=int(src.get("id")),
                video_id=uuid.UUID(src.get("video_id")),
                start_ms=int(src.get("start_ms", 0)),
                end_ms=int(src.get("end_ms", 0)),
                snippet=hl[0]
            ))
        total = data.get("hits", {}).get("total", {}).get("value") if isinstance(data.get("hits", {}).get("total"), dict) else None
        return SearchResponse(total=total, hits=hits)
    # Default Postgres FTS path
    if source == "native":
        rows = crud.search_segments(db, q=q, video_id=str(video_id) if video_id else None, limit=limit, offset=offset)
    else:
        rows = crud.search_youtube_segments(db, q=q, video_id=str(video_id) if video_id else None, limit=limit, offset=offset)
    hits = [SearchHit(id=r["id"], video_id=r["video_id"], start_ms=r["start_ms"], end_ms=r["end_ms"], snippet=r["snippet"] or "") for r in rows]
    return SearchResponse(hits=hits)

def _row_to_status(row):
    return JobStatus(
        id=row["id"],
        kind=row["kind"],
        state=row["state"],
        error=row["error"],
        created_at=row["created_at"],
        updated_at=row["updated_at"]
    )
