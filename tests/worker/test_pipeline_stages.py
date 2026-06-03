from __future__ import annotations

import sys
import uuid
from dataclasses import dataclass
from pathlib import Path
from unittest.mock import Mock

from types import ModuleType, SimpleNamespace

mock_ctx = Mock()
mock_ctx.__enter__ = Mock(return_value=mock_ctx)
mock_ctx.__exit__ = Mock(return_value=False)

mock_sdpa_kernel = Mock(return_value=mock_ctx)
mock_attention = SimpleNamespace(sdpa_kernel=mock_sdpa_kernel, SDPBackend=Mock())

mock_pydantic_settings = ModuleType("pydantic_settings")
setattr(mock_pydantic_settings, "BaseSettings", object)
setattr(mock_pydantic_settings, "SettingsConfigDict", dict)
sys.modules.setdefault("pydantic_settings", mock_pydantic_settings)

mock_torch = ModuleType("torch")
setattr(mock_torch, "cuda", SimpleNamespace(is_available=lambda: False))
setattr(mock_torch, "device", lambda *args, **kwargs: None)
setattr(mock_torch, "nn", SimpleNamespace(attention=mock_attention))
setattr(mock_torch, "backends", SimpleNamespace(cuda=SimpleNamespace(sdp_kernel=lambda *args, **kwargs: mock_ctx)))
sys.modules.setdefault("torch", mock_torch)

mock_torch_nn = ModuleType("torch.nn")
setattr(mock_torch_nn, "attention", mock_attention)
sys.modules.setdefault("torch.nn", mock_torch_nn)

mock_torch_nn_attention = ModuleType("torch.nn.attention")
setattr(mock_torch_nn_attention, "sdpa_kernel", mock_sdpa_kernel)
setattr(mock_torch_nn_attention, "SDPBackend", mock_attention.SDPBackend)
sys.modules.setdefault("torch.nn.attention", mock_torch_nn_attention)

mock_torch_backends = ModuleType("torch.backends")
setattr(mock_torch_backends, "cuda", SimpleNamespace(sdp_kernel=lambda *args, **kwargs: mock_ctx))
sys.modules.setdefault("torch.backends", mock_torch_backends)

mock_torch_backends_cuda = ModuleType("torch.backends.cuda")
setattr(mock_torch_backends_cuda, "sdp_kernel", lambda *args, **kwargs: mock_ctx)
sys.modules.setdefault("torch.backends.cuda", mock_torch_backends_cuda)

mock_faster_whisper = ModuleType("faster_whisper")
setattr(mock_faster_whisper, "WhisperModel", Mock())
sys.modules.setdefault("faster_whisper", mock_faster_whisper)

mock_whisper = ModuleType("whisper")
setattr(mock_whisper, "load_model", Mock())
sys.modules.setdefault("whisper", mock_whisper)

mock_sqlalchemy = ModuleType("sqlalchemy")
setattr(mock_sqlalchemy, "text", lambda value: value)
setattr(mock_sqlalchemy, "bindparam", lambda *args, **kwargs: None)
sys.modules.setdefault("sqlalchemy", mock_sqlalchemy)

mock_sqlalchemy_exc = ModuleType("sqlalchemy.exc")

class _SqlAlchemyError(Exception):
    pass


setattr(mock_sqlalchemy_exc, "OperationalError", _SqlAlchemyError)
setattr(mock_sqlalchemy_exc, "ProgrammingError", _SqlAlchemyError)
sys.modules.setdefault("sqlalchemy.exc", mock_sqlalchemy_exc)

mock_sqlalchemy_engine = ModuleType("sqlalchemy.engine")
setattr(mock_sqlalchemy_engine, "Engine", object)
sys.modules.setdefault("sqlalchemy.engine", mock_sqlalchemy_engine)


class _DummyMetric:
    def labels(self, *args, **kwargs):
        return self

    def observe(self, *args, **kwargs):
        return None

    def inc(self, *args, **kwargs):
        return None


mock_worker_metrics = ModuleType("worker.metrics")
for _metric_name in (
    "ytdlp_operation_attempts_total",
    "ytdlp_operation_duration_seconds",
    "ytdlp_operation_errors_total",
    "ytdlp_token_usage_total",
    "download_duration_seconds",
    "transcode_duration_seconds",
    "chunk_count",
    "transcription_duration_seconds",
    "whisper_chunk_transcription_seconds",
    "diarization_duration_seconds",
):
    setattr(mock_worker_metrics, _metric_name, _DummyMetric())
sys.modules.setdefault("worker.metrics", mock_worker_metrics)

from worker.audio import Chunk
from worker.native_pipeline import (
    NativePipelineDependencies,
    VideoPipelineContext,
    _download_and_transcode,
    _persist_transcript,
    _transcribe_chunks,
)


@dataclass
class _Settings:
    CHUNK_SECONDS: int = 900
    WHISPER_MODEL: str = "medium"
    WHISPER_LANGUAGE: str | None = None
    WHISPER_BEAM_SIZE: int = 5
    WHISPER_TEMPERATURE: float = 0.0
    WHISPER_WORD_TIMESTAMPS: bool = True
    WHISPER_VAD_FILTER: bool = False
    ENABLE_DIARIZATION: bool = False
    DIARIZATION_INLINE: bool = False
    ENABLE_CUSTOM_VOCABULARY: bool = False
    CLEANUP_AFTER_PROCESS: bool = False
    CLEANUP_DELETE_CHUNKS: bool = False
    CLEANUP_DELETE_WAV: bool = False
    CLEANUP_DELETE_RAW: bool = False
    CLEANUP_DELETE_DIR_IF_EMPTY: bool = False


def _mock_engine_with_video(video_row):
    conn = Mock()
    conn.__enter__ = Mock(return_value=conn)
    conn.__exit__ = Mock(return_value=False)
    conn.execute.return_value.mappings.return_value.first.return_value = video_row
    engine = Mock()
    engine.begin.return_value = conn
    return engine, conn


def test_download_and_transcode_stage_updates_video_state(tmp_path: Path):
    video_id = uuid.uuid4()
    job_id = uuid.uuid4()
    engine, conn = _mock_engine_with_video({"id": video_id, "youtube_id": "abc123", "job_id": job_id})
    ctx = VideoPipelineContext(engine=engine, video={"id": video_id, "youtube_id": "abc123", "job_id": job_id}, work_dir=tmp_path)

    raw_path = tmp_path / "raw.m4a"
    wav_path = tmp_path / "audio_16k.wav"
    download_audio_mock = Mock(return_value=raw_path)
    ensure_wav_16k_mock = Mock(return_value=wav_path)
    deps = NativePipelineDependencies(
        settings=_Settings(),
        logger=Mock(),
        download_audio=download_audio_mock,
        ensure_wav_16k=ensure_wav_16k_mock,
    )

    _download_and_transcode(ctx, deps)

    assert ctx.raw_path == raw_path
    assert ctx.wav_path == wav_path
    download_audio_mock.assert_called_once()
    ensure_wav_16k_mock.assert_called_once_with(raw_path)
    assert any("state='transcoding'" in str(call.args[0]) for call in conn.execute.call_args_list)
    assert any("state='transcribing'" in str(call.args[0]) for call in conn.execute.call_args_list)


def test_transcribe_stage_offsets_segments_and_detects_language(tmp_path: Path):
    video_id = uuid.uuid4()
    engine, _ = _mock_engine_with_video({"id": video_id, "youtube_id": "abc123", "job_id": uuid.uuid4()})
    ctx = VideoPipelineContext(
        engine=engine,
        video={"id": video_id, "youtube_id": "abc123", "job_id": uuid.uuid4()},
        work_dir=tmp_path,
        wav_path=tmp_path / "audio_16k.wav",
        quality_settings={"language": "en", "beam_size": 7, "temperature": 0.2, "word_timestamps": False, "vad_filter": True},
    )
    transcribe_chunk_mock = Mock(
        side_effect=[
            ([{"start": 0.0, "end": 1.0, "text": "first", "words": [{"start": 0.0, "end": 0.5}]}], {"language": "en", "language_probability": 0.99}),
            ([{"start": 0.0, "end": 1.0, "text": "second"}], {"language": "en", "language_probability": 0.99}),
        ]
    )
    deps = NativePipelineDependencies(
        settings=_Settings(),
        logger=Mock(),
        chunk_audio=Mock(return_value=[Chunk(path=tmp_path / "chunk_0000.wav", offset=0.0), Chunk(path=tmp_path / "chunk_0001.wav", offset=900.0)]),
        transcribe_chunk=transcribe_chunk_mock,
    )

    _transcribe_chunks(ctx, deps)

    assert ctx.detected_language == "en"
    assert ctx.language_probability == 0.99
    assert ctx.all_segments[0]["start"] == 0.0
    assert ctx.all_segments[1]["start"] == 900.0
    assert ctx.all_segments[0]["words"][0]["end"] == 0.5
    assert transcribe_chunk_mock.call_count == 2


def test_persist_stage_finalizes_video_and_refreshes_job(tmp_path: Path):
    video_id = uuid.uuid4()
    job_id = uuid.uuid4()
    engine, conn = _mock_engine_with_video({"id": video_id, "youtube_id": "abc123", "job_id": job_id})
    ctx = VideoPipelineContext(
        engine=engine,
        video={"id": video_id, "youtube_id": "abc123", "job_id": job_id},
        work_dir=tmp_path,
        diarization_state="skipped",
        diar_segments=[{"start": 0.0, "end": 1.0, "text": "hello", "speaker": None}],
        detected_language="en",
        language_probability=0.9,
    )
    refresh_job_state = Mock()
    replace_transcript_blocks = Mock()
    deps = NativePipelineDependencies(
        settings=_Settings(),
        logger=Mock(),
        replace_transcript_blocks=replace_transcript_blocks,
        refresh_job_state=refresh_job_state,
    )

    _persist_transcript(ctx, deps)

    assert replace_transcript_blocks.called
    assert refresh_job_state.called
    assert any("UPDATE videos" in str(call.args[0]) for call in conn.execute.call_args_list)
