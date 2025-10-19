import uuid

from sqlalchemy import text


def create_job(db, kind: str, url: str):
    job_id = uuid.uuid4()
    db.execute(
        text("INSERT INTO jobs (id, kind, input_url) VALUES (:i,:k,:u)"), {"i": str(job_id), "k": kind, "u": url}
    )
    db.commit()
    return job_id


def fetch_job(db, job_id):
    row = db.execute(text("SELECT * FROM jobs WHERE id=:i"), {"i": str(job_id)}).mappings().first()
    return row


def list_segments(db, video_id):
    rows = db.execute(
        text("SELECT start_ms,end_ms,text,speaker_label FROM segments WHERE video_id=:v ORDER BY start_ms"),
        {"v": str(video_id)},
    ).all()
    return rows


def get_video(db, video_id: uuid.UUID):
    return (
        db.execute(text("SELECT id, youtube_id, title, duration_seconds FROM videos WHERE id=:v"), {"v": str(video_id)})
        .mappings()
        .first()
    )


def list_videos(db, limit: int = 50, offset: int = 0):
    return (
        db.execute(
            text(
                """
            SELECT id, youtube_id, title, duration_seconds
            FROM videos
            ORDER BY created_at DESC
            LIMIT :limit OFFSET :offset
        """
            ),
            {"limit": limit, "offset": offset},
        )
        .mappings()
        .all()
    )


def get_youtube_transcript(db, video_id):
    return (
        db.execute(
            text("SELECT id, language, kind, full_text FROM youtube_transcripts WHERE video_id=:v"),
            {"v": str(video_id)},
        )
        .mappings()
        .first()
    )


def list_youtube_segments(db, youtube_transcript_id):
    return db.execute(
        text("SELECT start_ms,end_ms,text FROM youtube_segments WHERE youtube_transcript_id=:t ORDER BY start_ms"),
        {"t": str(youtube_transcript_id)},
    ).all()


def search_segments(db, q: str, video_id: str | None = None, limit: int = 50, offset: int = 0):
    sql = """
        SELECT id, video_id, start_ms, end_ms,
               ts_headline('english', text, websearch_to_tsquery('english', :q)) AS snippet,
               ts_rank_cd(text_tsv, websearch_to_tsquery('english', :q)) AS rank
        FROM segments
        WHERE text_tsv @@ websearch_to_tsquery('english', :q)
        {video_filter}
        ORDER BY rank DESC, start_ms ASC
        LIMIT :limit OFFSET :offset
    """
    video_filter = ""
    params = {"q": q, "limit": limit, "offset": offset}
    if video_id:
        video_filter = "AND video_id = :vid"
        params["vid"] = str(video_id)
    rows = db.execute(text(sql.format(video_filter=video_filter)), params).mappings().all()
    return rows


def search_youtube_segments(db, q: str, video_id: str | None = None, limit: int = 50, offset: int = 0):
    sql = """
        SELECT ys.id, yt.video_id, ys.start_ms, ys.end_ms,
               ts_headline('english', ys.text, websearch_to_tsquery('english', :q)) AS snippet,
               ts_rank_cd(ys.text_tsv, websearch_to_tsquery('english', :q)) AS rank
        FROM youtube_segments ys
        JOIN youtube_transcripts yt ON yt.id = ys.youtube_transcript_id
        WHERE ys.text_tsv @@ websearch_to_tsquery('english', :q)
        {video_filter}
        ORDER BY rank DESC, ys.start_ms ASC
        LIMIT :limit OFFSET :offset
    """
    video_filter = ""
    params = {"q": q, "limit": limit, "offset": offset}
    if video_id:
        video_filter = "AND yt.video_id = :vid"
        params["vid"] = str(video_id)
    rows = db.execute(text(sql.format(video_filter=video_filter)), params).mappings().all()
    return rows
