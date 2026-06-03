from __future__ import annotations

import uuid
from datetime import datetime
from io import BytesIO
from fastapi import APIRouter, Depends, Request, Response
from fastapi.responses import JSONResponse
from reportlab.lib import colors
from reportlab.lib.pagesizes import LETTER
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer
from sqlalchemy import text

from .. import crud
from ..common.session import get_session_token, get_user_from_session
from ..db import get_db
from ..exceptions import NotFoundError, TranscriptNotReadyError, VideoNotFoundError
from ..settings import settings
from ..transcripts.merged import build_merged_transcript
from ..transcripts.service import TranscriptPresentationService
from ..transcripts.types import TranscriptSegment
from ..transcripts.youtube_formatting import build_youtube_caption_blocks, format_youtube_caption_text

router = APIRouter(prefix="", tags=["Exports"])
transcript_presentation_service = TranscriptPresentationService()

SESSION_COOKIE = "tc_session"


def _fmt_time_ms(ms: int) -> str:
    s, ms_rem = divmod(int(ms), 1000)
    h, s = divmod(s, 3600)
    m, s = divmod(s, 60)
    return f"{h:02d}:{m:02d}:{s:02d},{ms_rem:03d}"


def _fmt_time_vtt(ms: int) -> str:
    s, ms_rem = divmod(int(ms), 1000)
    h, s = divmod(s, 3600)
    m, s = divmod(s, 60)
    return f"{h:02d}:{m:02d}:{s:02d}.{ms_rem:03d}"


def _block_to_payload(block):
    payload = {
        "block_index": block.block_index,
        "start_ms": block.start_ms,
        "end_ms": block.end_ms,
        "speaker_label": block.speaker_label,
        "text": block.text,
        "segment_ids": block.segment_ids,
        "kind": block.kind,
        "formatter_version": getattr(block, "formatter_version", "merged-v1"),
    }
    if hasattr(block, "primary_source"):
        payload.update(
            {
                "primary_source": block.primary_source,
                "supporting_sources": block.supporting_sources,
                "needs_review": block.needs_review,
                "merge_reason": block.merge_reason,
                "similarity": block.similarity,
            }
        )
    return payload


def _require_export_auth(
    db,
    request: Request,
    user,
    require_auth: bool = False,
):
    """Allow export access; only enforce login where explicitly required."""
    if require_auth and not user:
        return JSONResponse({"error": "auth_required", "message": "Login required to export."}, status_code=401)
    return None


def _log_export(db, request: Request, user, payload: dict):
    from ..metrics import exports_total

    db.execute(
        text("INSERT INTO events (user_id, session_token, type, payload) VALUES (:u,:t,'export',CAST(:p AS JSONB))"),
        {"u": str(user["id"]) if user else None, "t": get_session_token(request), "p": payload},
    )
    db.commit()

    # Track export metric
    fmt = payload.get("format", "unknown")
    exports_total.labels(format=fmt).inc()


def _load_best_export_source(db, video_id: uuid.UUID):
    """Return merged rows when possible, otherwise Whisper or formatted YouTube."""
    v = crud.get_video(db, video_id)
    if not v:
        raise VideoNotFoundError(str(video_id))

    segs = crud.list_segments(db, video_id)
    yt = crud.get_youtube_transcript(db, video_id)
    if segs and yt:
        whisper_segments = [transcript_presentation_service.from_db_row(r) for r in segs]
        yt_segs = crud.list_youtube_segments(db, yt["id"])
        youtube_segments = [TranscriptSegment(start_ms=r[0], end_ms=r[1], text=r[2], speaker_label=None) for r in yt_segs]
        merged = build_merged_transcript(str(video_id), whisper_segments, youtube_segments)
        cue_rows = [(s.start_ms, s.end_ms, s.text, s.speaker_label) for s in merged.segments]
        return "merged", v, cue_rows, merged.blocks

    if segs:
        return "native", v, segs, None

    if yt:
        yt_segs = crud.list_youtube_segments(db, yt["id"])
        blocks = build_youtube_caption_blocks([(r[0], r[1], r[2]) for r in yt_segs])
        return "youtube", v, yt_segs, blocks

    raise NotFoundError(
        message=f"Transcript for video {video_id} not found",
        resource_type="transcript",
        details={"video_id": str(video_id)},
    )


@router.get(
    "/videos/{video_id}/youtube-transcript.srt",
    summary="Export YouTube captions as SRT",
    description="""
    Download YouTube's native closed captions in SubRip (SRT) subtitle format.

    **Authentication Required:** Yes
    """,
    responses={
        200: {
            "description": "SRT file download",
            "content": {"text/plain": {"example": "1\n00:00:01,000 --> 00:00:03,500\nHello world\n\n"}},
        },
        401: {"description": "Authentication required"},
        503: {"description": "YouTube transcript not available"},
    },
)
def get_youtube_transcript_srt(video_id: uuid.UUID, request: Request, db=Depends(get_db)):
    """Export YouTube captions as SRT subtitle file."""
    yt = crud.get_youtube_transcript(db, video_id)
    if not yt:
        raise TranscriptNotReadyError(str(video_id), "no_youtube_transcript")
    user = get_user_from_session(db, get_session_token(request))
    gate = _require_export_auth(
        db,
        request,
        user,
        require_auth=True,
    )
    if gate is not None:
        return gate
    segs = crud.list_youtube_segments(db, yt["id"])
    blocks = build_youtube_caption_blocks([(r[0], r[1], r[2]) for r in segs])
    lines = []
    for i, block in enumerate(blocks, start=1):
        lines.append(str(i))
        lines.append(f"{_fmt_time_ms(block.start_ms)} --> {_fmt_time_ms(block.end_ms)}")
        lines.append(block.text)
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
    """,
    responses={
        200: {"description": "VTT file download"},
        401: {"description": "Authentication required"},
        503: {"description": "YouTube transcript not available"},
    },
)
def get_youtube_transcript_vtt(video_id: uuid.UUID, request: Request, db=Depends(get_db)):
    """Export YouTube captions as WebVTT subtitle file."""
    yt = crud.get_youtube_transcript(db, video_id)
    if not yt:
        raise TranscriptNotReadyError(str(video_id), "no_youtube_transcript")
    user = get_user_from_session(db, get_session_token(request))
    gate = _require_export_auth(
        db,
        request,
        user,
        require_auth=True,
    )
    if gate is not None:
        return gate
    segs = crud.list_youtube_segments(db, yt["id"])
    blocks = build_youtube_caption_blocks([(r[0], r[1], r[2]) for r in segs])

    lines = ["WEBVTT", ""]
    for block in blocks:
        lines.append(f"{_fmt_time_vtt(block.start_ms)} --> {_fmt_time_vtt(block.end_ms)}")
        lines.append(block.text)
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
    """,
    responses={
        200: {"description": "SRT file download"},
        401: {"description": "Authentication required"},
        503: {"description": "Transcript not ready"},
    },
)
def get_native_transcript_srt(video_id: uuid.UUID, request: Request, db=Depends(get_db)):
    """Export best available transcript as SRT subtitle file."""
    source, _v, segs, blocks = _load_best_export_source(db, video_id)
    user = get_user_from_session(db, get_session_token(request))
    gate = _require_export_auth(
        db,
        request,
        user,
        require_auth=source == "youtube",
    )
    if gate is not None:
        return gate
    lines = []
    if blocks is not None:
        cue_rows = [(block.start_ms, block.end_ms, block.text, None) for block in blocks]
    else:
        cue_rows = segs
    for i, (start_ms, end_ms, textv, _speaker) in enumerate(cue_rows, start=1):
        lines.append(str(i))
        lines.append(f"{_fmt_time_ms(start_ms)} --> {_fmt_time_ms(end_ms)}")
        lines.append(textv)
        lines.append("")
    body = "\n".join(lines)
    _log_export(db, request, user, {"format": "srt", "source": source, "policy": "best", "video_id": str(video_id)})
    suffix = ".youtube" if source == "youtube" else (".merged" if source == "merged" else "")
    headers = {"Content-Disposition": f"attachment; filename=video-{video_id}{suffix}.srt"}
    return Response(content=body, media_type="text/plain", headers=headers)


@router.get(
    "/videos/{video_id}/transcript.vtt",
    summary="Export Whisper transcript as VTT",
    description="""
    Download Whisper-generated transcript in WebVTT subtitle format.

    **Authentication Required:** Yes
    """,
    responses={
        200: {"description": "VTT file download"},
        401: {"description": "Authentication required"},
        503: {"description": "Transcript not ready"},
    },
)
def get_native_transcript_vtt(video_id: uuid.UUID, request: Request, db=Depends(get_db)):
    """Export best available transcript as WebVTT subtitle file."""
    source, _v, segs, blocks = _load_best_export_source(db, video_id)
    user = get_user_from_session(db, get_session_token(request))
    gate = _require_export_auth(
        db,
        request,
        user,
        require_auth=source == "youtube",
    )
    if gate is not None:
        return gate

    lines = ["WEBVTT", ""]
    if blocks is not None:
        cue_rows = [(block.start_ms, block.end_ms, block.text, None) for block in blocks]
    else:
        cue_rows = segs
    for start_ms, end_ms, textv, _speaker in cue_rows:
        lines.append(f"{_fmt_time_vtt(start_ms)} --> {_fmt_time_vtt(end_ms)}")
        lines.append(textv)
        lines.append("")
    body = "\n".join(lines)
    _log_export(db, request, user, {"format": "vtt", "source": source, "policy": "best", "video_id": str(video_id)})
    suffix = ".youtube" if source == "youtube" else (".merged" if source == "merged" else "")
    headers = {"Content-Disposition": f"attachment; filename=video-{video_id}{suffix}.vtt"}
    return Response(content=body, media_type="text/vtt", headers=headers)


@router.get(
    "/videos/{video_id}/transcript.json",
    summary="Export Whisper transcript as JSON",
    description="""
    Download Whisper-generated transcript in JSON format with full segment data.

    **Authentication Required:** Yes
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
        503: {"description": "Transcript not ready"},
    },
)
def get_native_transcript_json(video_id: uuid.UUID, request: Request, db=Depends(get_db)):
    """Export best available transcript as JSON."""
    source, _v, segs, blocks = _load_best_export_source(db, video_id)
    user = get_user_from_session(db, get_session_token(request))
    gate = _require_export_auth(
        db,
        request,
        user,
        require_auth=source == "youtube",
    )
    if gate is not None:
        return gate
    if source == "youtube":
        payload = {
            "video_id": str(video_id),
            "source": "youtube",
            "source_label": "YouTube captions",
            "segments": [{"start_ms": r[0], "end_ms": r[1], "text": r[2]} for r in segs],
            "full_text": "\n\n".join(block.text for block in (blocks or [])),
            "blocks": [_block_to_payload(block) for block in (blocks or [])],
        }
    elif source == "merged":
        payload = {
            "video_id": str(video_id),
            "source": "merged",
            "source_label": "Merged transcript",
            "segments": [
                {"start_ms": r[0], "end_ms": r[1], "text": r[2], "speaker_label": r[3]}
                for r in segs
            ],
            "full_text": "\n\n".join(block.text for block in (blocks or [])),
            "blocks": [_block_to_payload(block) for block in (blocks or [])],
        }
    else:
        payload = {
            "video_id": str(video_id),
            "source": "whisper",
            "source_label": "Whisper transcript",
            "segments": [{"start_ms": r[0], "end_ms": r[1], "text": r[2], "speaker_label": r[3]} for r in segs],
        }
    _log_export(db, request, user, {"format": "json", "source": source, "policy": "best", "video_id": str(video_id)})
    suffix = ".youtube" if source == "youtube" else (".merged" if source == "merged" else "")
    headers = {"Content-Disposition": f"attachment; filename=video-{video_id}{suffix}.json"}
    return JSONResponse(payload, headers=headers)


@router.get(
    "/videos/{video_id}/youtube-transcript.json",
    summary="Export YouTube captions as JSON",
    description="""
    Download YouTube's native closed captions in JSON format.

    **Authentication Required:** Yes
    """,
    responses={
        200: {"description": "JSON file download"},
        401: {"description": "Authentication required"},
        503: {"description": "YouTube transcript not available"},
    },
)
def get_youtube_transcript_json(video_id: uuid.UUID, request: Request, db=Depends(get_db)):
    """Export YouTube captions as JSON."""
    user = get_user_from_session(db, get_session_token(request))
    gate = _require_export_auth(
        db,
        request,
        user,
        require_auth=True,
    )
    if gate is not None:
        return gate
    yt = crud.get_youtube_transcript(db, video_id)
    if not yt:
        raise TranscriptNotReadyError(str(video_id), "no_youtube_transcript")
    segs = crud.list_youtube_segments(db, yt["id"])
    blocks = build_youtube_caption_blocks([(r[0], r[1], r[2]) for r in segs])
    payload = {
        "video_id": str(video_id),
        "language": yt.get("language"),
        "kind": yt.get("kind"),
        "segments": [{"start_ms": r[0], "end_ms": r[1], "text": r[2]} for r in segs],
        "full_text": format_youtube_caption_text([(r[0], r[1], r[2]) for r in segs]),
        "blocks": [_block_to_payload(block) for block in blocks],
    }
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
    """,
    responses={
        200: {"description": "PDF file download", "content": {"application/pdf": {}}},
        401: {"description": "Authentication required"},
        503: {"description": "Transcript not ready"},
    },
)
def get_native_transcript_pdf(video_id: uuid.UUID, request: Request, db=Depends(get_db)):
    """Export Whisper transcript as formatted PDF."""
    # Check resource existence before auth gating
    v = crud.get_video(db, video_id)
    if not v:
        from ..exceptions import VideoNotFoundError

        raise VideoNotFoundError(str(video_id))
    segs = crud.list_segments(db, video_id)
    if not segs:
        from ..exceptions import NotFoundError

        raise NotFoundError(
            message=f"Transcript for video {video_id} not found",
            resource_type="transcript",
            details={"video_id": str(video_id)},
        )

    user = get_user_from_session(db, get_session_token(request))
    gate = _require_export_auth(
        db,
        request,
        user,
    )
    if gate is not None:
        return gate
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
