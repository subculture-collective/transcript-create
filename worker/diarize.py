import os

from app.logging_config import get_logger
from app.settings import settings

logger = get_logger(__name__)

_pipeline = None
_pyannote_import_error = None


def _get_pipeline():
    global _pipeline
    if _pipeline is None:
        if not settings.ENABLE_DIARIZATION:
            logger.info("Diarization disabled; returning Whisper segments")
            return None
        if not settings.HF_TOKEN:
            logger.warning("ENABLE_DIARIZATION is true but HF_TOKEN is missing; skipping diarization")
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
            _pipeline = Pipeline.from_pretrained(settings.DIARIZATION_MODEL, token=settings.HF_TOKEN)
        except Exception as e:
            logger.warning("Failed to initialize pyannote Pipeline; skipping diarization", extra={"error": str(e)})
            try:
                # Fallback to older model
                _pipeline = Pipeline.from_pretrained(settings.DIARIZATION_FALLBACK_MODEL, token=settings.HF_TOKEN)
            except Exception as e2:
                logger.warning("Fallback pipeline also failed; skipping diarization", extra={"error": str(e2)})
                _pipeline = None
        if _pipeline is not None:
            device = settings.DIARIZATION_DEVICE.strip().lower()
            if device and device != "auto":
                try:
                    import torch

                    if device == "cuda" and not torch.cuda.is_available():
                        logger.warning(
                            "DIARIZATION_DEVICE=cuda requested but CUDA is not available; "
                            "leaving pyannote device unchanged"
                        )
                    elif hasattr(_pipeline, "to"):
                        _pipeline.to(torch.device(device))
                        logger.info("Diarization pipeline moved to device", extra={"device": device})
                except Exception as e:
                    logger.warning(
                        "Failed to move diarization pipeline to requested device",
                        extra={"device": device, "error": str(e)},
                    )
    return _pipeline


def _build_audio_input(wav_path):
    """Build pyannote input while avoiding torchcodec path decoding when possible.

    pyannote.audio 4.x may try to decode file paths through torchcodec. The CUDA
    image currently pins Torch/Torchaudio for GTX 1080 compatibility, which can
    leave torchcodec unavailable or incompatible. Passing a preloaded waveform
    keeps diarization optional and prevents that decoder mismatch from breaking
    the worker.
    """
    try:
        import torchaudio  # type: ignore

        waveform, sample_rate = torchaudio.load(str(wav_path))
        return {"waveform": waveform, "sample_rate": sample_rate}
    except Exception as e:
        logger.warning(
            "Failed to preload audio for diarization; falling back to path input",
            extra={"error": str(e)},
        )
        return {"audio": str(wav_path)}


def run_diarization(wav_path):
    """Run pyannote diarization and return raw diarization tracks.

    Unlike diarize_and_align, this does not swallow pyannote exceptions. Use it
    from the standalone worker where failures should be visible/retryable by DB
    state rather than hidden as unlabeled transcript segments.
    """
    pipe = _get_pipeline()
    if pipe is None:
        raise RuntimeError("Diarization pipeline not available")
    logger.info("Running diarization", extra={"wav_path": str(wav_path)})
    diar_input = _build_audio_input(wav_path)
    diar_output = pipe(diar_input) if callable(pipe) else pipe(str(wav_path))
    diar = getattr(diar_output, "speaker_diarization", diar_output)
    diar_list = []
    label_first_time = {}
    for seg, _track, label in diar.itertracks(yield_label=True):
        diar_list.append((seg.start, seg.end, label))
        if label not in label_first_time:
            label_first_time[label] = seg.start
    ordered_labels = sorted(label_first_time.items(), key=lambda kv: kv[1])
    friendly = {raw: f"Speaker {i + 1}" for i, (raw, _t) in enumerate(ordered_labels)}
    logger.info("Diarization produced speaker segments", extra={"segment_count": len(diar_list)})
    return diar_list, friendly


def diarize_and_align(wav_path, whisper_segments):
    try:
        pipe = _get_pipeline()
        if pipe is None:
            logger.info("Diarization pipeline not available; returning whisper segments as-is")
            return whisper_segments
        diar_list, friendly = run_diarization(wav_path)
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
        logger.info(
            "Diarization assigned speakers to segments",
            extra={"speakers_assigned": speakers_assigned, "total_segments": len(whisper_segments)},
        )
        return diar_segments
    except Exception as e:
        logger.warning("Diarization failed; returning Whisper segments as-is", extra={"error": str(e)})
        return whisper_segments
