import os
import warnings
from typing import Any, Optional

import torch

from app.logging_config import get_logger
from app.settings import settings

# Suppress PyTorch weights_only FutureWarning for trusted Whisper models
warnings.filterwarnings("ignore", category=FutureWarning, message=".*torch.load.*weights_only.*")
warnings.filterwarnings("ignore", category=FutureWarning, module="whisper")

logger = get_logger(__name__)

_ct2: Optional[Any] = None
_torch_whisper: Optional[Any] = None

_model: Optional[Any] = None
_fallback_ct2_model: Optional[Any] = None


def _lazy_imports():
    global _ct2, _torch_whisper
    if settings.WHISPER_BACKEND == "faster-whisper" and _ct2 is None:
        try:
            from faster_whisper import WhisperModel as CT2Model

            _ct2 = CT2Model
        except ImportError:
            logger.error("Failed to import faster-whisper. Ensure it is installed.")
            # _ct2 remains None
    if settings.WHISPER_BACKEND == "whisper" and _torch_whisper is None:
        try:
            import whisper as torch_whisper

            _torch_whisper = torch_whisper
        except ImportError:
            logger.error("Failed to import whisper. Ensure openai-whisper is installed.")
            # _torch_whisper remains None


def _try_load_ct2(model_name: str, device: str, compute_type: str):
    _lazy_imports()
    if settings.WHISPER_BACKEND == "faster-whisper" and _ct2 is None:
        raise RuntimeError("faster-whisper backend not loaded")
    logger.info(
        "Loading faster-whisper model",
        extra={"model": model_name, "device": device, "compute_type": compute_type},
    )
    return _ct2(model_name, device=device, compute_type=compute_type)


def _try_load_torch(model_name: str, force_gpu: bool):
    _lazy_imports()
    if settings.WHISPER_BACKEND == "whisper" and _torch_whisper is None:
        raise RuntimeError("whisper backend not loaded")
    # For ROCm, torch.device("cuda") maps to HIP when ROCm builds are installed
    use_cuda = torch.cuda.is_available()
    if force_gpu and not use_cuda:
        raise RuntimeError("FORCE_GPU is true but torch.cuda is not available")
    device = torch.device("cuda" if use_cuda else "cpu")
    logger.info("Loading openai-whisper model", extra={"model": model_name, "device": str(device)})

    # Suppress weights_only FutureWarning for trusted OpenAI models
    with warnings.catch_warnings():
        warnings.filterwarnings("ignore", category=FutureWarning, message=".*torch.load.*weights_only.*")
        return _torch_whisper.load_model(model_name, device=str(device))


def _get_model():
    from worker.metrics import whisper_model_load_seconds
    import time
    
    global _model
    if _model is None:
        load_start = time.time()
        if settings.WHISPER_BACKEND == "whisper":
            # PyTorch Whisper path (ROCm-compatible when torch is ROCm build)
            _model = _try_load_torch(settings.WHISPER_MODEL, settings.FORCE_GPU)
        else:
            # faster-whisper (CTranslate2) path
            if settings.FORCE_GPU:
                devices = [d.strip() for d in settings.GPU_DEVICE_PREFERENCE.split(",") if d.strip()]
                compute_types = [c.strip() for c in settings.GPU_COMPUTE_TYPES.split(",") if c.strip()]
                models = [m.strip() for m in settings.GPU_MODEL_FALLBACKS.split(",") if m.strip()]
                if settings.WHISPER_MODEL not in models:
                    models.insert(0, settings.WHISPER_MODEL)
                else:
                    models = [settings.WHISPER_MODEL] + [m for m in models if m != settings.WHISPER_MODEL]

                last_err = None
                for dev in devices:
                    for model_name in models:
                        for ctype in compute_types:
                            try:
                                logger.info(
                                    "FORCE_GPU enabled - trying configuration",
                                    extra={"device": dev, "model": model_name, "compute_type": ctype},
                                )
                                _model = _try_load_ct2(model_name, device=dev, compute_type=ctype)
                                logger.info(
                                    "Model loaded on GPU successfully",
                                    extra={"device": dev, "model": model_name, "compute_type": ctype},
                                )
                                # Removed duplicate metric observation to prevent double counting.
                                return _model
                            except Exception as e:
                                last_err = e
                                logger.warning(
                                    "GPU load failed",
                                    extra={
                                        "device": dev,
                                        "model": model_name,
                                        "compute_type": ctype,
                                        "error": str(e),
                                    },
                                )
                                continue
                raise RuntimeError(f"FORCE_GPU is true but no GPU configuration succeeded: {last_err}")
            else:
                # Device auto, try half then float32
                try:
                    _model = _try_load_ct2(settings.WHISPER_MODEL, device="auto", compute_type="float16")
                except Exception:
                    logger.warning("Half precision failed; retrying with float32 on device=auto")
                    _model = _try_load_ct2(settings.WHISPER_MODEL, device="auto", compute_type="float32")
        
        load_duration = time.time() - load_start
        whisper_model_load_seconds.labels(model=settings.WHISPER_MODEL, backend=settings.WHISPER_BACKEND).observe(load_duration)
        logger.info("Model loaded", extra={"duration_seconds": round(load_duration, 2)})
    return _model


def _get_ct2_fallback_model():
    """Load a ROCm HIP CTranslate2 model as a fallback when PyTorch whisper crashes on ROCm."""
    global _fallback_ct2_model
    if _fallback_ct2_model is None:
        try_order = [
            (settings.WHISPER_MODEL, "auto", "float32"),
            # If the exact model fails, try stepping down once for stability
            ("medium", "auto", "float32"),
        ]
        last_err = None
        for model_name, dev, ctype in try_order:
            try:
                _fallback_ct2_model = _try_load_ct2(model_name, device=dev, compute_type=ctype)
                logging.info("CT2 fallback loaded: model=%s device=%s compute=%s", model_name, dev, ctype)
                break
            except Exception as e:
                last_err = e
                logging.warning("CT2 fallback load failed (model=%s dev=%s compute=%s): %s", model_name, dev, ctype, e)
        if _fallback_ct2_model is None:
            raise RuntimeError(f"Unable to load CT2 fallback model on ROCm HIP: {last_err}")
    return _fallback_ct2_model


def transcribe_chunk(wav_path, language=None, beam_size=None, temperature=None, word_timestamps=None):
    """Transcribe audio chunk with Whisper.
    
    Args:
        wav_path: Path to audio file
        language: Language code (e.g., 'en', 'es') or None for auto-detect
        beam_size: Beam size for decoding (default: from settings or 5)
        temperature: Sampling temperature (default: from settings or 0.0)
        word_timestamps: Extract word-level timestamps (default: from settings)
    
    Returns:
        Tuple of (segments_list, language_info_dict)
    """
    model = _get_model()
    
    # Use settings defaults if not specified
    if beam_size is None:
        beam_size = getattr(settings, 'WHISPER_BEAM_SIZE', 5)
    if temperature is None:
        temperature = getattr(settings, 'WHISPER_TEMPERATURE', 0.0)
    if word_timestamps is None:
        word_timestamps = getattr(settings, 'WHISPER_WORD_TIMESTAMPS', True)
    if language is None:
        language = getattr(settings, 'WHISPER_LANGUAGE', None) or None
    
    logging.info("Transcribing %s (lang=%s, beam=%d, temp=%.1f, word_ts=%s)", 
                 wav_path, language or "auto", beam_size, temperature, word_timestamps)
    
    detected_language = None
    language_probability = None
    
    if settings.WHISPER_BACKEND == "whisper":
        # openai-whisper returns dict with 'segments' list
        # On ROCm, some optimized attention kernels can cause faults on certain drivers/GPUs.
        # Force fp32 and disable flash/mem-efficient attention so math kernels are used.
        # Best-effort: use runtime toggles; also set env fallbacks for future imports.
        os.environ.setdefault("PYTORCH_SDP_DISABLE_FLASH_ATTENTION", "1")
        os.environ.setdefault("PYTORCH_SDP_DISABLE_MEM_EFFICIENT_ATTENTION", "1")
        os.environ.setdefault("PYTORCH_SDP_DISABLE_FUSED_ATTENTION", "1")

        # Use new PyTorch API (torch.nn.attention.sdpa_kernel) with fallback for older versions
        try:
            from torch.nn.attention import SDPBackend, sdpa_kernel

            # Use MATH backend only (equivalent to enable_math=True, others=False)
            def new_sdp_ctx():
                return sdpa_kernel([SDPBackend.MATH])

            sdp_ctx = new_sdp_ctx
        except ImportError:
            # Fallback to deprecated API for older PyTorch versions
            sdp_ctx_func = getattr(getattr(torch.backends, "cuda", object()), "sdp_kernel", None)
            if callable(sdp_ctx_func):

                def old_sdp_ctx():
                    return sdp_ctx_func(enable_flash=False, enable_mem_efficient=False, enable_math=True)

                sdp_ctx = old_sdp_ctx
            else:
                sdp_ctx = None

        try:
            transcribe_kwargs = {
                "fp16": False,
                "beam_size": beam_size,
                "temperature": temperature,
            }
            if language:
                transcribe_kwargs["language"] = language
            if word_timestamps:
                transcribe_kwargs["word_timestamps"] = True
                
            if sdp_ctx:
                with sdp_ctx():
                    result = model.transcribe(str(wav_path), **transcribe_kwargs)
            else:
                result = model.transcribe(str(wav_path), **transcribe_kwargs)
                
            detected_language = result.get("language")
            
        except Exception as e:
            # Known ROCm fault signatures
            msg = str(e)
            if "Memory access fault" in msg or "hipError" in msg or "HSA_STATUS_ERROR" in msg:
                logging.error("PyTorch whisper on ROCm crashed (%s). Falling back to CT2 HIP backend.", msg)
                ct2 = _get_ct2_fallback_model()
                ct2_kwargs = {"beam_size": beam_size}
                if language:
                    ct2_kwargs["language"] = language
                if word_timestamps:
                    ct2_kwargs["word_timestamps"] = True
                segments, info = ct2.transcribe(str(wav_path), **ct2_kwargs)
                detected_language = info.language if hasattr(info, 'language') else None
                language_probability = info.language_probability if hasattr(info, 'language_probability') else None
                out = []
                for s in segments:
                    seg_dict = {
                        "start": s.start,
                        "end": s.end,
                        "text": s.text.strip(),
                        "avg_logprob": s.avg_logprob,
                        "temperature": s.temperature,
                        "token_count": len(s.tokens),
                        "confidence": getattr(s, "no_speech_prob", None),
                    }
                    if word_timestamps and hasattr(s, 'words'):
                        seg_dict["words"] = [
                            {"word": w.word, "start": w.start, "end": w.end, "probability": w.probability}
                            for w in s.words
                        ]
                    out.append(seg_dict)
                lang_info = {
                    "language": detected_language,
                    "language_probability": language_probability,
                }
                return out, lang_info
            else:
                raise
        out = []
        for seg in result.get("segments", []):
            seg_dict = {
                "start": float(seg.get("start", 0)),
                "end": float(seg.get("end", 0)),
                "text": (seg.get("text") or "").strip(),
                "avg_logprob": seg.get("avg_logprob"),
                "temperature": seg.get("temperature"),
                "token_count": len(seg.get("tokens") or []),
                "confidence": None,
            }
            if word_timestamps and "words" in seg:
                seg_dict["words"] = seg["words"]
            out.append(seg_dict)
        lang_info = {"language": detected_language, "language_probability": None}
        return out, lang_info
    else:
        # faster-whisper backend
        ct2_kwargs = {"beam_size": beam_size, "temperature": temperature}
        if language:
            ct2_kwargs["language"] = language
        if word_timestamps:
            ct2_kwargs["word_timestamps"] = True
            
        segments, info = model.transcribe(str(wav_path), **ct2_kwargs)
        logging.debug("Transcribe info: %s", info)
        
        detected_language = info.language if hasattr(info, 'language') else None
        language_probability = info.language_probability if hasattr(info, 'language_probability') else None
        
        out = []
        for s in segments:
            seg_dict = {
                "start": s.start,
                "end": s.end,
                "text": s.text.strip(),
                "avg_logprob": s.avg_logprob,
                "temperature": s.temperature,
                "token_count": len(s.tokens),
                "confidence": getattr(s, "no_speech_prob", None),
            }
            if word_timestamps and hasattr(s, 'words'):
                seg_dict["words"] = [
                    {"word": w.word, "start": w.start, "end": w.end, "probability": w.probability}
                    for w in s.words
                ]
            out.append(seg_dict)
        
        lang_info = {
            "language": detected_language,
            "language_probability": language_probability,
        }
        return out, lang_info
