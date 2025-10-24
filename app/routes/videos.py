import uuid

from fastapi import APIRouter, Depends

from .. import crud
from ..db import get_db
from ..exceptions import TranscriptNotReadyError, VideoNotFoundError
from ..schemas import Segment, TranscriptResponse, VideoInfo, YouTubeTranscriptResponse, YTSegment

router = APIRouter()


@router.get("/videos/{video_id}/transcript", response_model=TranscriptResponse)
def get_transcript(video_id: uuid.UUID, db=Depends(get_db)):
    # Check if video exists
    video = crud.get_video(db, video_id)
    if not video:
        raise VideoNotFoundError(str(video_id))

    segs = crud.list_segments(db, video_id)
    if not segs:
        # Check if video is still processing
        raise TranscriptNotReadyError(str(video_id), "processing")

    return TranscriptResponse(
        video_id=video_id, segments=[Segment(start_ms=r[0], end_ms=r[1], text=r[2], speaker_label=r[3]) for r in segs]
    )


@router.get("/videos/{video_id}", response_model=VideoInfo)
def get_video_info(video_id: uuid.UUID, db=Depends(get_db)):
    v = crud.get_video(db, video_id)
    if not v:
        raise VideoNotFoundError(str(video_id))
    return VideoInfo(
        id=v["id"], youtube_id=v["youtube_id"], title=v.get("title"), duration_seconds=v.get("duration_seconds")
    )


@router.get("/videos", response_model=list[VideoInfo])
def list_videos(limit: int = 50, offset: int = 0, db=Depends(get_db)):
    rows = crud.list_videos(db, limit=limit, offset=offset)
    return [
        VideoInfo(
            id=r["id"], youtube_id=r["youtube_id"], title=r.get("title"), duration_seconds=r.get("duration_seconds")
        )
        for r in rows
    ]


@router.get("/videos/{video_id}/youtube-transcript", response_model=YouTubeTranscriptResponse)
def get_youtube_transcript(video_id: uuid.UUID, db=Depends(get_db)):
    # Check if video exists
    video = crud.get_video(db, video_id)
    if not video:
        raise VideoNotFoundError(str(video_id))

    yt = crud.get_youtube_transcript(db, video_id)
    if not yt:
        raise TranscriptNotReadyError(str(video_id), "no_youtube_transcript")

    segs = crud.list_youtube_segments(db, yt["id"])
    return YouTubeTranscriptResponse(
        video_id=video_id,
        language=yt.get("language"),
        kind=yt.get("kind"),
        full_text=yt.get("full_text"),
        segments=[YTSegment(start_ms=r[0], end_ms=r[1], text=r[2]) for r in segs],
    )
