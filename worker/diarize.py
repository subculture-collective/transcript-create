import logging
import os
from app.settings import settings

_pipeline = None
_pyannote_import_error = None

def _get_pipeline():
    global _pipeline
    if _pipeline is None:
        if not settings.HF_TOKEN:
            logging.warning("HF_TOKEN missing; skipping diarization (returning Whisper segments)")
            return None
        # Lazy import to avoid hard dependency when diarization isn't needed
        try:
            from pyannote.audio import Pipeline  # type: ignore
        except Exception as ie:
            global _pyannote_import_error
            _pyannote_import_error = ie
            logging.warning("pyannote.audio not available (%s); skipping diarization", ie)
            return None
        os.environ.setdefault("HUGGINGFACE_HUB_TOKEN", settings.HF_TOKEN)
        os.environ.setdefault("HF_TOKEN", settings.HF_TOKEN)
        try:
            _pipeline = Pipeline.from_pretrained("pyannote/speaker-diarization")
        except TypeError:
            try:
                _pipeline = Pipeline.from_pretrained("pyannote/speaker-diarization", token=settings.HF_TOKEN)
            except Exception as e:
                logging.warning("Failed to initialize pyannote Pipeline: %s; skipping diarization", e)
                _pipeline = None
    return _pipeline

def diarize_and_align(wav_path, whisper_segments):
    try:
        pipe = _get_pipeline()
        if pipe is None:
            return whisper_segments
        logging.info("Running diarization on %s", wav_path)
        diar = pipe(str(wav_path))
        diar_list = []
        for seg, speaker in diar.itertracks(yield_label=True):
            diar_list.append((seg.start, seg.end, speaker))
        logging.info("Diarization produced %d speaker segments", len(diar_list))
        diar_segments = []
        for w in whisper_segments:
            w_mid = (w["start"] + w["end"]) / 2.0
            speaker = None
            for ds in diar_list:
                if w_mid >= ds[0] and w_mid <= ds[1]:
                    speaker = ds[2]
                    break
            w["speaker"] = speaker
            diar_segments.append(w)
        return diar_segments
    except Exception as e:
        logging.warning("Diarization failed (%s); returning Whisper segments as-is", e)
        return whisper_segments
