from __future__ import annotations

import uuid
from datetime import datetime
from io import BytesIO
from typing import Optional

from fastapi import APIRouter, Depends, Request, Response
from fastapi.responses import JSONResponse, RedirectResponse
from reportlab.lib import colors
from reportlab.lib.pagesizes import LETTER
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer
from sqlalchemy import text

from .. import crud
from ..common.session import get_session_token, get_user_from_session, is_admin
from ..db import get_db
from ..exceptions import TranscriptNotReadyError
from ..settings import settings

router = APIRouter(prefix="", tags=["Exports"])

SESSION_COOKIE = "tc_session"


def _fmt_time_ms(ms: int) -> str:
    s, ms_rem = divmod(int(ms), 1000)
    h, s = divmod(s, 3600)
    m, s = divmod(s, 60)
    return f"{h:02d}:{m:02d}:{s:02d},{ms_rem:03d}"


def _export_allowed_or_402(db, request: Request, user, redirect_to: Optional[str] = None):
    # Pro users and admins allowed
    if user and (is_admin(user) or (user.get("plan") or "free").lower() == settings.PRO_PLAN_NAME.lower()):
        return None
    # For free users, enforce soft daily export limit
    uid = str(user["id"]) if user else None
    if uid:
        used = db.execute(
            text(
                """
            SELECT COUNT(*) FROM events
            WHERE user_id=:u AND type='export'
              AND created_at >= date_trunc('day', now() AT TIME ZONE 'UTC')
        """
            ),
            {"u": uid},
        ).scalar_one()
        if used >= settings.FREE_DAILY_EXPORT_LIMIT:
            accept = (request.headers.get("accept") or "").lower()
            if "text/html" in accept and redirect_to:
                return RedirectResponse(url=redirect_to, status_code=307)
            return JSONResponse(
                {"error": "upgrade_required", "message": "Daily export limit reached. Upgrade to Pro."},
                status_code=402,
            )
    else:
        # Unauthed cannot export
        return JSONResponse({"error": "auth_required", "message": "Login required to export."}, status_code=401)
    return None


def _log_export(db, request: Request, user, payload: dict):
    db.execute(
        text("INSERT INTO events (user_id, session_token, type, payload) VALUES (:u,:t,'export',:p)"),
        {"u": str(user["id"]) if user else None, "t": get_session_token(request), "p": payload},
    )
    db.commit()


@router.get(
    "/videos/{video_id}/youtube-transcript.srt",
    summary="Export YouTube captions as SRT",
    description="""
    Download YouTube's native closed captions in SubRip (SRT) subtitle format.
    
    **Authentication Required:** Yes  
    **Rate Limits:** Free plan limited to daily export quota
    """,
    responses={
        200: {
            "description": "SRT file download",
            "content": {"text/plain": {"example": "1\n00:00:01,000 --> 00:00:03,500\nHello world\n\n"}},
        },
        401: {"description": "Authentication required"},
        402: {"description": "Daily export limit reached (free plan)"},
        503: {"description": "YouTube transcript not available"},
    },
)
def get_youtube_transcript_srt(video_id: uuid.UUID, request: Request, db=Depends(get_db)):
    """Export YouTube captions as SRT subtitle file."""
    user = get_user_from_session(db, get_session_token(request))
    gate = _export_allowed_or_402(
        db, request, user, redirect_to=f"{settings.FRONTEND_ORIGIN}/upgrade?redirect=/v/{video_id}"
    )
    if gate is not None:
        return gate
    yt = crud.get_youtube_transcript(db, video_id)
    if not yt:
        raise TranscriptNotReadyError(str(video_id), "no_youtube_transcript")
    segs = crud.list_youtube_segments(db, yt["id"])
    lines = []
    for i, (start_ms, end_ms, textv) in enumerate(segs, start=1):
        lines.append(str(i))
        lines.append(f"{_fmt_time_ms(start_ms)} --> {_fmt_time_ms(end_ms)}")
        lines.append(textv)
        lines.append("")
    body = "\n".join(lines)
    _log_export(db, request, user, {"format": "srt", "source": "youtube", "video_id": str(video_id)})
    headers = {"Content-Disposition": f"attachment; filename=video-{video_id}.youtube.srt"}
    return Response(content=body, media_type="text/plain", headers=headers)


@router.get(
    "/videos/{video_id}/youtube-transcript.vtt",
    summary="Export YouTube captions as VTT",
    description="""
    Download YouTube's native closed captions in WebVTT subtitle format.
    
    **Authentication Required:** Yes  
    **Rate Limits:** Free plan limited to daily export quota
    """,
    responses={
        200: {"description": "VTT file download"},
        401: {"description": "Authentication required"},
        402: {"description": "Daily export limit reached (free plan)"},
        503: {"description": "YouTube transcript not available"},
    },
)
def get_youtube_transcript_vtt(video_id: uuid.UUID, request: Request, db=Depends(get_db)):
    """Export YouTube captions as WebVTT subtitle file."""
    user = get_user_from_session(db, get_session_token(request))
    gate = _export_allowed_or_402(
        db, request, user, redirect_to=f"{settings.FRONTEND_ORIGIN}/upgrade?redirect=/v/{video_id}"
    )
    if gate is not None:
        return gate
    yt = crud.get_youtube_transcript(db, video_id)
    if not yt:
        raise TranscriptNotReadyError(str(video_id), "no_youtube_transcript")
    segs = crud.list_youtube_segments(db, yt["id"])

    def vtt_time(ms: int) -> str:
        s, ms_rem = divmod(ms, 1000)
        h, s = divmod(s, 3600)
        m, s = divmod(s, 60)
        return f"{h:02d}:{m:02d}:{s:02d}.{ms_rem:03d}"

    lines = ["WEBVTT", ""]
    for start_ms, end_ms, textv in segs:
        lines.append(f"{vtt_time(start_ms)} --> {vtt_time(end_ms)}")
        lines.append(textv)
        lines.append("")
    body = "\n".join(lines)
    _log_export(db, request, user, {"format": "vtt", "source": "youtube", "video_id": str(video_id)})
    headers = {"Content-Disposition": f"attachment; filename=video-{video_id}.youtube.vtt"}
    return Response(content=body, media_type="text/vtt", headers=headers)


@router.get(
    "/videos/{video_id}/transcript.srt",
    summary="Export Whisper transcript as SRT",
    description="""
    Download Whisper-generated transcript in SubRip (SRT) subtitle format.
    
    **Authentication Required:** Yes  
    **Rate Limits:** Free plan limited to daily export quota
    """,
    responses={
        200: {"description": "SRT file download"},
        401: {"description": "Authentication required"},
        402: {"description": "Daily export limit reached (free plan)"},
        503: {"description": "Transcript not ready"},
    },
)
def get_native_transcript_srt(video_id: uuid.UUID, request: Request, db=Depends(get_db)):
    """Export Whisper transcript as SRT subtitle file."""
    user = get_user_from_session(db, get_session_token(request))
    gate = _export_allowed_or_402(
        db, request, user, redirect_to=f"{settings.FRONTEND_ORIGIN}/upgrade?redirect=/v/{video_id}"
    )
    if gate is not None:
        return gate
    segs = crud.list_segments(db, video_id)
    if not segs:
        raise TranscriptNotReadyError(str(video_id), "no_segments")
    lines = []
    for i, (start_ms, end_ms, textv, _speaker) in enumerate(segs, start=1):
        lines.append(str(i))
        lines.append(f"{_fmt_time_ms(start_ms)} --> {_fmt_time_ms(end_ms)}")
        lines.append(textv)
        lines.append("")
    body = "\n".join(lines)
    _log_export(db, request, user, {"format": "srt", "source": "native", "video_id": str(video_id)})
    headers = {"Content-Disposition": f"attachment; filename=video-{video_id}.srt"}
    return Response(content=body, media_type="text/plain", headers=headers)


@router.get(
    "/videos/{video_id}/transcript.vtt",
    summary="Export Whisper transcript as VTT",
    description="""
    Download Whisper-generated transcript in WebVTT subtitle format.
    
    **Authentication Required:** Yes  
    **Rate Limits:** Free plan limited to daily export quota
    """,
    responses={
        200: {"description": "VTT file download"},
        401: {"description": "Authentication required"},
        402: {"description": "Daily export limit reached (free plan)"},
        503: {"description": "Transcript not ready"},
    },
)
def get_native_transcript_vtt(video_id: uuid.UUID, request: Request, db=Depends(get_db)):
    """Export Whisper transcript as WebVTT subtitle file."""
    user = get_user_from_session(db, get_session_token(request))
    gate = _export_allowed_or_402(
        db, request, user, redirect_to=f"{settings.FRONTEND_ORIGIN}/upgrade?redirect=/v/{video_id}"
    )
    if gate is not None:
        return gate
    segs = crud.list_segments(db, video_id)
    if not segs:
        raise TranscriptNotReadyError(str(video_id), "no_segments")

    def vtt_time(ms: int) -> str:
        s, ms_rem = divmod(ms, 1000)
        h, s = divmod(s, 3600)
        m, s = divmod(s, 60)
        return f"{h:02d}:{m:02d}:{s:02d}.{ms_rem:03d}"

    lines = ["WEBVTT", ""]
    for start_ms, end_ms, textv, _speaker in segs:
        lines.append(f"{vtt_time(start_ms)} --> {vtt_time(end_ms)}")
        lines.append(textv)
        lines.append("")
    body = "\n".join(lines)
    _log_export(db, request, user, {"format": "vtt", "source": "native", "video_id": str(video_id)})
    headers = {"Content-Disposition": f"attachment; filename=video-{video_id}.vtt"}
    return Response(content=body, media_type="text/vtt", headers=headers)


@router.get(
    "/videos/{video_id}/transcript.json",
    summary="Export Whisper transcript as JSON",
    description="""
    Download Whisper-generated transcript in JSON format with full segment data.
    
    **Authentication Required:** Yes  
    **Rate Limits:** Free plan limited to daily export quota
    """,
    responses={
        200: {
            "description": "JSON file download",
            "content": {
                "application/json": {
                    "example": [
                        {
                            "start_ms": 1000,
                            "end_ms": 3500,
                            "text": "Hello world",
                            "speaker_label": "Speaker 1",
                        }
                    ]
                }
            },
        },
        401: {"description": "Authentication required"},
        402: {"description": "Daily export limit reached (free plan)"},
        503: {"description": "Transcript not ready"},
    },
)
def get_native_transcript_json(video_id: uuid.UUID, request: Request, db=Depends(get_db)):
    """Export Whisper transcript as JSON."""
    user = get_user_from_session(db, get_session_token(request))
    gate = _export_allowed_or_402(
        db, request, user, redirect_to=f"{settings.FRONTEND_ORIGIN}/upgrade?redirect=/v/{video_id}"
    )
    if gate is not None:
        return gate
    segs = crud.list_segments(db, video_id)
    if not segs:
        raise TranscriptNotReadyError(str(video_id), "no_segments")
    payload = [{"start_ms": r[0], "end_ms": r[1], "text": r[2], "speaker_label": r[3]} for r in segs]
    _log_export(db, request, user, {"format": "json", "source": "native", "video_id": str(video_id)})
    headers = {"Content-Disposition": f"attachment; filename=video-{video_id}.json"}
    return JSONResponse(payload, headers=headers)


@router.get(
    "/videos/{video_id}/youtube-transcript.json",
    summary="Export YouTube captions as JSON",
    description="""
    Download YouTube's native closed captions in JSON format.
    
    **Authentication Required:** Yes  
    **Rate Limits:** Free plan limited to daily export quota
    """,
    responses={
        200: {"description": "JSON file download"},
        401: {"description": "Authentication required"},
        402: {"description": "Daily export limit reached (free plan)"},
        503: {"description": "YouTube transcript not available"},
    },
)
def get_youtube_transcript_json(video_id: uuid.UUID, request: Request, db=Depends(get_db)):
    """Export YouTube captions as JSON."""
    user = get_user_from_session(db, get_session_token(request))
    gate = _export_allowed_or_402(
        db, request, user, redirect_to=f"{settings.FRONTEND_ORIGIN}/upgrade?redirect=/v/{video_id}"
    )
    if gate is not None:
        return gate
    yt = crud.get_youtube_transcript(db, video_id)
    if not yt:
        raise TranscriptNotReadyError(str(video_id), "no_youtube_transcript")
    segs = crud.list_youtube_segments(db, yt["id"])
    payload = [{"start_ms": r[0], "end_ms": r[1], "text": r[2]} for r in segs]
    _log_export(db, request, user, {"format": "json", "source": "youtube", "video_id": str(video_id)})
    headers = {"Content-Disposition": f"attachment; filename=video-{video_id}.youtube.json"}
    return JSONResponse(payload, headers=headers)


@router.get(
    "/videos/{video_id}/transcript.pdf",
    summary="Export Whisper transcript as PDF",
    description="""
    Download Whisper-generated transcript as a formatted PDF document.
    
    The PDF includes:
    - Video title and metadata
    - Timestamps for each segment
    - Speaker labels (if diarization was performed)
    - Formatted for easy reading and printing
    
    **Authentication Required:** Yes  
    **Rate Limits:** Free plan limited to daily export quota
    """,
    responses={
        200: {"description": "PDF file download", "content": {"application/pdf": {}}},
        401: {"description": "Authentication required"},
        402: {"description": "Daily export limit reached (free plan)"},
        503: {"description": "Transcript not ready"},
    },
)
def get_native_transcript_pdf(video_id: uuid.UUID, request: Request, db=Depends(get_db)):
    """Export Whisper transcript as formatted PDF."""
    user = get_user_from_session(db, get_session_token(request))
    gate = _export_allowed_or_402(
        db, request, user, redirect_to=f"{settings.FRONTEND_ORIGIN}/upgrade?redirect=/v/{video_id}"
    )
    if gate is not None:
        return gate
    segs = crud.list_segments(db, video_id)
    if not segs:
        raise TranscriptNotReadyError(str(video_id), "no_segments")
    # Build PDF in-memory
    buf = BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=LETTER,
        leftMargin=0.9 * inch,
        rightMargin=0.9 * inch,
        topMargin=1.1 * inch,
        bottomMargin=0.9 * inch,
    )
    styles = getSampleStyleSheet()
    # Register a serif font with priority: settings.PDF_FONT_PATH -> DejaVuSerif -> Times-Roman
    base_font = "Times-Roman"
    if settings.PDF_FONT_PATH:
        try:
            pdfmetrics.registerFont(TTFont("CustomSerif", settings.PDF_FONT_PATH))
            base_font = "CustomSerif"
        except Exception:
            pass
    if base_font == "Times-Roman":
        try:
            pdfmetrics.registerFont(TTFont("DejaVuSerif", "/usr/share/fonts/truetype/dejavu/DejaVuSerif.ttf"))
            base_font = "DejaVuSerif"
        except Exception:
            pass
    heading = ParagraphStyle(
        name="Heading", parent=styles["Heading2"], fontName=base_font, textColor=colors.black, spaceAfter=12
    )
    body = ParagraphStyle(name="Body", parent=styles["BodyText"], fontName=base_font, fontSize=11, leading=15)
    time = ParagraphStyle(
        name="Time", parent=styles["BodyText"], fontName=base_font, fontSize=9, textColor=colors.grey, spaceAfter=2
    )
    story: list = []
    # Title and header/footer + metadata
    v = crud.get_video(db, video_id)
    title = (v.get("title") if v else None) or f"Transcript {video_id}"
    duration = v.get("duration_seconds") if v else None
    platform = "YouTube"
    date_str = datetime.utcnow().strftime("%Y-%m-%d")
    story.append(Paragraph(title, heading))
    story.append(Spacer(1, 6))
    # Segments
    for start_ms, _end_ms, textv, speaker in segs:
        hhmmss = _fmt_time_ms(start_ms).replace(",", ".")
        ts = Paragraph(hhmmss, time)
        story.append(ts)
        content = textv if textv else ""
        if speaker:
            content = f"<b>{speaker}:</b> {content}"
        story.append(Paragraph(content, body))
        story.append(Spacer(1, 4))

    # Header/footer drawing
    def _header_footer(canvas, doc_obj):
        canvas.saveState()
        canvas.setFont(base_font, 9)
        # Header title
        canvas.setFillColor(colors.grey)
        canvas.drawString(doc.leftMargin, doc.height + doc.topMargin - 0.6 * inch, title)
        # Metadata line (right-aligned)
        meta = []
        if duration:
            h = duration // 3600
            m = (duration % 3600) // 60
            s = duration % 60
            meta.append(f"{h:02d}:{m:02d}:{s:02d}")
        meta.append(platform)
        meta.append(date_str)
        canvas.drawRightString(doc.width + doc.leftMargin, doc.height + doc.topMargin - 0.6 * inch, " • ".join(meta))
        # Footer page number
        page = canvas.getPageNumber()
        canvas.drawRightString(doc.width + doc.leftMargin, 0.5 * inch, f"Page {page}")
        canvas.restoreState()

    doc.build(story, onFirstPage=_header_footer, onLaterPages=_header_footer)
    pdf = buf.getvalue()
    buf.close()
    _log_export(db, request, user, {"format": "pdf", "source": "native", "video_id": str(video_id)})
    headers = {"Content-Disposition": f"attachment; filename=video-{video_id}.pdf"}
    return Response(content=pdf, media_type="application/pdf", headers=headers)
