import os

from app.logging_config import get_logger
from app.settings import settings

logger = get_logger(__name__)

_pipeline = None
_pyannote_import_error = None


def _get_pipeline():
    global _pipeline
    if _pipeline is None:
        if not settings.HF_TOKEN:
            logger.warning("HF_TOKEN missing; skipping diarization (returning Whisper segments)")
            return None
        # Lazy import to avoid hard dependency when diarization isn't needed
        try:
            from pyannote.audio import Pipeline  # type: ignore
        except Exception as ie:
            global _pyannote_import_error
            _pyannote_import_error = ie
            logger.warning("pyannote.audio not available; skipping diarization", extra={"error": str(ie)})
            return None
        os.environ.setdefault("HUGGINGFACE_HUB_TOKEN", settings.HF_TOKEN)
        os.environ.setdefault("HF_TOKEN", settings.HF_TOKEN)
        try:
            _pipeline = Pipeline.from_pretrained("pyannote/speaker-diarization-community-1", token=settings.HF_TOKEN)
        except Exception as e:
            logger.warning("Failed to initialize pyannote Pipeline; skipping diarization", extra={"error": str(e)})
            try:
                # Fallback to older model
                _pipeline = Pipeline.from_pretrained("pyannote/speaker-diarization", token=settings.HF_TOKEN)
            except Exception as e2:
                logger.warning("Fallback pipeline also failed; skipping diarization", extra={"error": str(e2)})
                _pipeline = None
    return _pipeline


def diarize_and_align(wav_path, whisper_segments):
    try:
        pipe = _get_pipeline()
        if pipe is None:
            logger.info("Diarization pipeline not available; returning whisper segments as-is")
            return whisper_segments
        logging.info("Running diarization on %s", wav_path)
        # pyannote Pipeline accepts raw path or dict with key 'audio'
        diar = pipe({"audio": str(wav_path)}) if callable(pipe) else pipe(str(wav_path))
        diar_list = []
        # itertracks(yield_label=True) yields (segment, track, label)
        label_first_time = {}
        for seg, _track, label in diar.itertracks(yield_label=True):
            diar_list.append((seg.start, seg.end, label))
            # record first occurrence to derive stable speaker ordering
            if label not in label_first_time:
                label_first_time[label] = seg.start
        logging.info("Diarization produced %d speaker segments", len(diar_list))
        # Build friendly names like "Speaker 1", "Speaker 2" based on first appearance
        ordered_labels = sorted(label_first_time.items(), key=lambda kv: kv[1])
        friendly = {raw: f"Speaker {i + 1}" for i, (raw, _t) in enumerate(ordered_labels)}
        diar_segments = []
        speakers_assigned = 0
        for w in whisper_segments:
            w_mid = (w["start"] + w["end"]) / 2.0
            speaker = None
            for ds in diar_list:
                if w_mid >= ds[0] and w_mid <= ds[1]:
                    # map raw label (e.g., SPEAKER_00) to friendly name
                    speaker = friendly.get(ds[2], ds[2])
                    speakers_assigned += 1
                    break
            # Persist as both 'speaker' (raw) and 'speaker_label' (API/DB expected field)
            w["speaker"] = speaker
            w["speaker_label"] = speaker
            diar_segments.append(w)
        logging.info("Diarization assigned speakers to %d/%d segments", speakers_assigned, len(whisper_segments))
        return diar_segments
    except Exception as e:
        logging.warning("Diarization failed (%s); returning Whisper segments as-is", e)
        return whisper_segments
