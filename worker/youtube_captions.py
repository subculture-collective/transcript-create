import json
import logging
import subprocess
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple
from urllib.request import Request, urlopen

from app.logging_config import get_logger

logger = get_logger(__name__)


@dataclass
class YTSegment:
    start: float
    end: float
    text: str


@dataclass
class YTCaptionTrack:
    url: str
    language: Optional[str]
    kind: str  # 'auto' or 'manual'
    ext: str  # 'json3', 'vtt', etc.


def _build_metadata_strategies() -> List[Tuple[str, List[str]]]:
    """Build list of client strategies for metadata extraction.

    Returns list of (client_name, extractor_args) tuples.
    """
    from app.settings import settings
    from worker.ytdlp_client_utils import get_client_extractor_args

    strategies = []
    client_order = [c.strip() for c in settings.YTDLP_CLIENT_ORDER.split(",") if c.strip()]
    disabled_clients = set(c.strip() for c in settings.YTDLP_CLIENTS_DISABLED.split(",") if c.strip())

    for client in client_order:
        if client in disabled_clients:
            continue

        extractor_args = get_client_extractor_args(client)
        if extractor_args:
            strategies.append((client, extractor_args))
        else:
            logger.warning(f"Unknown YTDLP client '{client}' in YTDLP_CLIENT_ORDER; skipping.")

    if not strategies:
        strategies.append(("default", []))

    return strategies


def _yt_dlp_json(url: str) -> Dict[str, Any]:
    """Return yt-dlp JSON metadata for a YouTube URL using client fallback strategy."""
    from pathlib import Path

    from app.settings import settings

    strategies = _build_metadata_strategies()

    last_error = None
    for client_name, extractor_args in strategies:
        cmd = ["yt-dlp", "-J"]
        cmd.extend(extractor_args)

        # Add cookies if configured
        if settings.YTDLP_COOKIES_PATH and Path(settings.YTDLP_COOKIES_PATH).exists():
            cmd.extend(["--cookies", settings.YTDLP_COOKIES_PATH])

        cmd.append(url)

        try:
            logger.info(f"Fetching metadata with client: {client_name}")
            meta = subprocess.check_output(cmd, stderr=subprocess.PIPE, text=True)
            return json.loads(meta)
        except subprocess.CalledProcessError as e:
            last_error = e
            logger.warning(f"Metadata fetch failed with {client_name}: {e.returncode}")
        except Exception as e:
            last_error = e
            logger.warning(f"Metadata fetch raised exception with {client_name}: {e}")

    # All strategies failed
    if last_error:
        raise last_error
    raise RuntimeError("Failed to fetch metadata with all client strategies")


def _pick_auto_caption(data: dict) -> Optional[YTCaptionTrack]:
    """Select an auto-generated caption track if available.

    yt-dlp JSON typically contains `automatic_captions` keyed by language code.
    We prefer English variants first, otherwise pick the first available.
    """
    auto = data.get("automatic_captions") or {}
    if not auto:
        return None
    # Preferred order of language keys
    prefs = ["en", "en-US", "en-GB"]
    # Prefer json3, then vtt
    prefer_ext_order = ["json3", "vtt"]
    candidates: List[Tuple[str, str, str]] = []  # (lang, url, ext)
    for lang, tracks in auto.items():
        for t in tracks:
            ext = t.get("ext")
            if ext in ("json3", "vtt") and t.get("url"):
                candidates.append((lang, t.get("url"), ext))
    if not candidates:
        return None
    # choose preferred language and preferred ext
    for ext in prefer_ext_order:
        for p in prefs:
            for lang, u, e in candidates:
                if lang == p and e == ext:
                    return YTCaptionTrack(url=u, language=lang, kind="auto", ext=e)
        # fallback to any language for this ext
        for lang, u, e in candidates:
            if e == ext:
                return YTCaptionTrack(url=u, language=lang, kind="auto", ext=e)
    # else pick first
    lang, u, e = candidates[0]
    return YTCaptionTrack(url=u, language=lang, kind="auto", ext=e)


def _parse_vtt_to_segments(vtt_bytes: bytes) -> List[YTSegment]:
    def parse_ts(ts: str) -> float:
        # HH:MM:SS.mmm or MM:SS.mmm
        ts = ts.strip()
        parts = ts.split(":")
        if len(parts) == 3:
            h, m, s = parts
            sec, ms = (s.replace(",", ".").split(".") + ["0"])[:2]
            return int(h) * 3600 + int(m) * 60 + int(sec) + int(ms[:3]) / 1000.0
        elif len(parts) == 2:
            m, s = parts
            sec, ms = (s.replace(",", ".").split(".") + ["0"])[:2]
            return int(m) * 60 + int(sec) + int(ms[:3]) / 1000.0
        return 0.0

    text = vtt_bytes.decode(errors="ignore").splitlines()
    segs: List[YTSegment] = []
    i = 0
    # Skip WEBVTT header if present
    if i < len(text) and text[i].strip().upper().startswith("WEBVTT"):
        i += 1
    # Skip optional header metadata lines until blank
    while i < len(text) and text[i].strip() != "":
        i += 1
    # Consume blank
    while i < len(text) and text[i].strip() == "":
        i += 1
    while i < len(text):
        # Optional cue id
        if i < len(text) and text[i].strip() and "-->" not in text[i]:
            i += 1
        if i >= len(text):
            break
        if "-->" not in text[i]:
            i += 1
            continue
        timing = text[i].strip()
        i += 1
        try:
            left, right = timing.split("-->")
            start = parse_ts(left)
            end = parse_ts(right)
        except Exception:
            # Malformed timing line, skip block
            while i < len(text) and text[i].strip() != "":
                i += 1
            while i < len(text) and text[i].strip() == "":
                i += 1
            continue
        lines = []
        while i < len(text) and text[i].strip() != "":
            lines.append(text[i].strip())
            i += 1
        # consume blank
        while i < len(text) and text[i].strip() == "":
            i += 1
        cue = " ".join(lines).strip()
        if cue:
            segs.append(YTSegment(start=start, end=end, text=cue))
    return segs


def fetch_youtube_auto_captions(youtube_id: str) -> Optional[tuple[YTCaptionTrack, List[YTSegment]]]:
    """Fetch auto captions (json3) for a given YouTube video id and parse to segments.

    Returns (track, segments) or None if unavailable.
    """
    url = f"https://www.youtube.com/watch?v={youtube_id}"
    logging.info("Probing yt-dlp metadata for captions: %s", url)
    data = _yt_dlp_json(url)
    track = _pick_auto_caption(data)
    if not track:
        logging.info("No auto captions found for %s", youtube_id)
        return None
    logging.info("Downloading captions: lang=%s ext=%s", track.language, track.ext)
    # Download via stdlib (no extra deps)
    try:
        req = Request(track.url, headers={"User-Agent": "Mozilla/5.0"})
        with urlopen(req, timeout=20) as resp:
            payload = resp.read()
    except Exception as e:
        logging.warning("Failed to download captions (%s): %s", track.ext, e)
        return None
    segments: List[YTSegment] = []
    if track.ext == "json3":
        try:
            j = json.loads(payload)
        except Exception as e:
            logging.warning("Invalid json3 payload: %s", e)
            return None
        # json3 structure has 'events' with 'tStartMs' and 'dDurationMs'; text in 'segs'
        for ev in j.get("events", []) or []:
            start_ms = ev.get("tStartMs")
            dur_ms = ev.get("dDurationMs") or 0
            segs = ev.get("segs") or []
            if start_ms is None or not segs:
                continue
            text_parts = []
            for s in segs:
                t = s.get("utf8")
                if not t:
                    continue
                text_parts.append(t)
            text_joined = ("".join(text_parts)).strip()
            if not text_joined:
                continue
            start = float(start_ms) / 1000.0
            end = start + (float(dur_ms) / 1000.0 if dur_ms else 0.0)
            segments.append(YTSegment(start=start, end=end, text=text_joined))
    elif track.ext == "vtt":
        try:
            segments = _parse_vtt_to_segments(payload)
        except Exception as e:
            logging.warning("Failed to parse VTT: %s", e)
            return None
    else:
        logging.info("Unsupported caption ext: %s", track.ext)
        return None
    return track, segments
