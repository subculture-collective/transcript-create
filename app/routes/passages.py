"""Public, server-readable passage pages; no stored selections or media acquisition."""

import html
import re
import textwrap
import uuid
from io import BytesIO
from urllib.parse import urlencode, urlsplit

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from fastapi.responses import HTMLResponse
from PIL import Image, ImageDraw, ImageFont
from sqlalchemy import text

from ..db import get_db
from ..settings import settings

router = APIRouter(tags=["Passages"])
MAX_TIME_MS = 2_147_483_647


def passage_time(ms: int) -> str:
    seconds, millis = divmod(ms, 1000)
    hours, seconds = divmod(seconds, 3600)
    minutes, seconds = divmod(seconds, 60)
    return f"{hours:02}:{minutes:02}:{seconds:02}" + (f".{millis:03}" if millis else "")


def public_origin() -> str:
    origin = settings.FRONTEND_ORIGIN.rstrip("/")
    parsed = urlsplit(origin)
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.netloc
        or parsed.username
        or parsed.path
        or parsed.query
        or parsed.fragment
    ):
        raise HTTPException(503, "Public archive origin is not configured")
    return origin


def load_passage(db, video_id: uuid.UUID, start_ms: int, end_ms: int) -> dict:
    if not settings.PUBLIC_PASSAGES_ENABLED:
        raise HTTPException(404, "Public passage sharing is disabled")
    if end_ms <= start_ms:
        raise HTTPException(422, "End time must be after start time")
    # Deliberately bypass cached video/transcript helpers: deletion must immediately
    # stop serving text and cards. This deployment exposes a public archive only.
    video = (
        db.execute(
            text("SELECT id, title, youtube_id, duration_seconds, uploaded_at FROM videos WHERE id=:id"),
            {"id": video_id},
        )
        .mappings()
        .first()
    )
    if not video:
        raise HTTPException(404, "Recording unavailable")
    if video["duration_seconds"] and end_ms > video["duration_seconds"] * 1000:
        raise HTTPException(422, "Passage exceeds the recording duration")
    params = {"id": video_id, "start": start_ms, "end": end_ms}
    rows = (
        db.execute(
            text("""
        SELECT start_ms, end_ms, left(text, 2000) AS text FROM segments
        WHERE video_id=:id AND end_ms>:start AND start_ms<:end
        ORDER BY start_ms, id LIMIT 12
    """),
            params,
        )
        .mappings()
        .all()
    )
    if not rows:
        rows = (
            db.execute(
                text("""
            SELECT s.start_ms, s.end_ms, left(s.text, 2000) AS text
            FROM youtube_segments s JOIN youtube_transcripts t ON t.id=s.youtube_transcript_id
            WHERE t.video_id=:id AND s.end_ms>:start AND s.start_ms<:end
            ORDER BY s.start_ms, s.id LIMIT 12
        """),
                params,
            )
            .mappings()
            .all()
        )
    if not rows:
        raise HTTPException(404, "No public transcript is available for this passage")
    return {"video": dict(video), "rows": [dict(row) for row in rows], "start_ms": start_ms, "end_ms": end_ms}


def passage_urls(video_id: uuid.UUID, start_ms: int, end_ms: int) -> tuple[str, str, str]:
    origin = public_origin()
    query = urlencode({"start_ms": start_ms, "end_ms": end_ms})
    page = f"{origin}/api/share/videos/{video_id}?{query}"
    image = f"{origin}/api/share/videos/{video_id}/card.png?{query}"
    player = (
        f"{origin}/v/{video_id}?"
        + urlencode({"t": start_ms // 1000, "t_ms": start_ms, "end_ms": end_ms})
        + f"#moment-{start_ms}"
    )
    return page, image, player


@router.get(
    "/share/videos/{video_id}", response_class=HTMLResponse, summary="Open a public passage with social metadata"
)
def passage_page(
    video_id: uuid.UUID,
    start_ms: int = Query(ge=0, le=MAX_TIME_MS),
    end_ms: int = Query(gt=0, le=MAX_TIME_MS),
    db=Depends(get_db),
):
    passage = load_passage(db, video_id, start_ms, end_ms)
    video = passage["video"]
    title = str(video["title"] or "Archive recording")[:300]
    times = f"{passage_time(start_ms)}–{passage_time(end_ms)}"
    excerpt = " ".join(" ".join(row["text"].split()) for row in passage["rows"])[:500]
    page_url, image_url, player_url = passage_urls(video_id, start_ms, end_ms)
    esc = html.escape
    paragraphs = "".join(
        f'<p><time>{passage_time(row["start_ms"])}</time> {esc(row["text"])}</p>' for row in passage["rows"]
    )
    youtube_id = str(video["youtube_id"] or "")
    embed = ""
    if re.fullmatch(r"[A-Za-z0-9_-]{11}", youtube_id):
        embed = f'<iframe title="Source video" src="https://www.youtube.com/embed/{youtube_id}?start={start_ms // 1000}&amp;end={(end_ms + 999) // 1000}" allow="encrypted-media; fullscreen; picture-in-picture" allowfullscreen referrerpolicy="strict-origin-when-cross-origin"></iframe>'
    palette = settings.SITE_BRANDING.theme.dark
    canvas = palette.get("canvas", "#0f0f0f")
    ink = palette.get("ink", "#eeeae1")
    accent = palette.get("accent", "#ff5b52")
    body = f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{esc(title)} · {times}</title><meta name="description" content="{esc(excerpt)}">
<meta property="og:type" content="article"><meta property="og:title" content="{esc(title)} · {times}">
<meta property="og:description" content="{esc(excerpt)}"><meta property="og:url" content="{esc(page_url)}">
<meta property="og:image" content="{esc(image_url)}"><meta property="og:image:type" content="image/png"><meta property="og:image:width" content="1200"><meta property="og:image:height" content="630">
<meta name="twitter:card" content="summary_large_image"><link rel="canonical" href="{esc(page_url)}">
<style>body{{margin:0;background:{canvas};color:{ink};font:18px/1.65 system-ui}}main{{max-width:850px;margin:3rem auto;padding:1.5rem}}h1{{line-height:1.2}}a{{color:{accent}}}time{{color:{accent};font:14px monospace}}iframe{{width:100%;aspect-ratio:16/9;border:0;min-height:210px}}.note{{color:#b8b6be;font-size:14px}}.action{{display:inline-block;padding:12px 18px;border:1px solid {accent};border-radius:8px}}</style></head>
<body><main><p>{esc(settings.SITE_NAME)} · Shared passage</p><h1>{esc(title)}</h1><p>{times}</p>
{embed}<p><a class="action" href="{esc(player_url)}">Open passage, adjust selection and read surrounding context</a></p>
<h2>Transcript excerpt</h2>{paragraphs}<p class="note">This excerpt shows up to 12 overlapping transcript segments. Automated wording and timing may be approximate. Verify quotations against the source; the link does not preserve removed media.</p></main></body></html>"""
    return HTMLResponse(
        body,
        headers={
            "Cache-Control": "no-store",
            "X-Robots-Tag": "noindex",
            "Content-Security-Policy": "default-src 'none'; style-src 'unsafe-inline'; frame-src https://www.youtube.com; base-uri 'none'; form-action 'none'; frame-ancestors 'none'",
        },
    )


@router.get("/share/videos/{video_id}/card.png", response_class=Response, summary="Render a passage social card")
def passage_card(
    video_id: uuid.UUID,
    start_ms: int = Query(ge=0, le=MAX_TIME_MS),
    end_ms: int = Query(gt=0, le=MAX_TIME_MS),
    db=Depends(get_db),
):
    passage = load_passage(db, video_id, start_ms, end_ms)
    palette = settings.SITE_BRANDING.theme.dark
    image = Image.new("RGB", (1200, 630), palette.get("canvas", "#0f0f0f"))
    draw = ImageDraw.Draw(image)
    draw.rectangle((0, 0, 18, 630), fill=palette.get("accent", "#ff5b52"))
    font = ImageFont.load_default(size=38)
    small = ImageFont.load_default(size=26)
    draw.text((60, 42), settings.SITE_NAME[:60], font=small, fill=palette.get("accent", "#ff5b52"))
    title = str(passage["video"]["title"] or "Archive recording")[:200]
    draw.multiline_text(
        (60, 102), "\n".join(textwrap.wrap(title, 48)[:3]), font=font, fill=palette.get("ink", "#eeeae1"), spacing=10
    )
    excerpt = " ".join(passage["rows"][0]["text"].split())[:300]
    draw.multiline_text((60, 290), "\n".join(textwrap.wrap(excerpt, 66)[:5]), font=small, fill="#ceccd4", spacing=9)
    draw.text(
        (60, 550),
        f"{passage_time(start_ms)} - {passage_time(end_ms)} | Source and context",
        font=small,
        fill=palette.get("accent", "#ff5b52"),
    )
    output = BytesIO()
    image.save(output, format="PNG")
    return Response(output.getvalue(), media_type="image/png", headers={"Cache-Control": "no-store"})
