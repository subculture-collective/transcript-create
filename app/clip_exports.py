"""Bounded local-original clip spool. No acquisition, remote inputs, or public files."""

from __future__ import annotations

import fcntl
import hashlib
import json
import math
import shutil
import subprocess
import time
from contextlib import contextmanager
from pathlib import Path
from uuid import UUID, uuid4

MAX_SOURCE_BYTES = 10 * 1024**3
MAX_OUTPUT_BYTES = 100 * 1024**2
MAX_DURATION_MS = 120_000
TTL_SECONDS = 24 * 3600


class ClipError(ValueError):
    pass


def digest(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            value.update(chunk)
    return value.hexdigest()


def probe(path: Path) -> dict:
    result = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-protocol_whitelist",
            "file,pipe",
            "-show_entries",
            "format=duration,format_name:stream=codec_type,width,height",
            "-of",
            "json",
            str(path),
        ],
        check=True,
        capture_output=True,
        timeout=20,
    )
    data = json.loads(result.stdout)
    duration = float(data.get("format", {}).get("duration", 0))
    formats = set(data.get("format", {}).get("format_name", "").split(","))
    if not formats.intersection({"mov", "mp4", "matroska", "webm"}) or not math.isfinite(duration) or duration <= 0:
        raise ClipError("Use a finite MP4/MOV/WebM/Matroska original")
    video = next((s for s in data.get("streams", []) if s.get("codec_type") == "video"), None)
    if not video or not 0 < video.get("width", 0) <= 7680 or not 0 < video.get("height", 0) <= 4320:
        raise ClipError("Original must contain video no larger than 7680 × 4320")
    return {"duration_ms": round(duration * 1000), "format": "mov" if "mov" in formats else "matroska"}


class ClipStore:
    def __init__(self, spool: Path, originals: Path):
        self.spool = spool.resolve()
        self.originals = originals.resolve(strict=True)
        if (
            not self.originals.is_dir()
            or self.spool == self.originals
            or self.spool.is_relative_to(self.originals)
            or self.originals.is_relative_to(self.spool)
        ):
            raise ClipError("Use separate originals and private spool directories")
        self.spool.mkdir(parents=True, exist_ok=True, mode=0o700)
        if self.spool.stat().st_mode & 0o077:
            raise ClipError("Spool directory must be private (chmod 700)")
        for name in ("sources", "jobs"):
            (self.spool / name).mkdir(exist_ok=True, mode=0o700)

    @contextmanager
    def lock(self):
        with (self.spool / ".lock").open("a") as lock:
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as exc:
                raise ClipError("The local renderer is busy; please retry shortly") from exc
            try:
                yield
            finally:
                fcntl.flock(lock, fcntl.LOCK_UN)

    def record_path(self, kind: str, key: str) -> Path:
        return self.spool / kind / f"{UUID(str(key))}.json"

    def load(self, kind: str, key: str) -> dict:
        path = self.record_path(kind, key)
        if not path.is_file():
            raise ClipError("Clip or authorized original not found")
        return dict(json.loads(path.read_text()))

    def save(self, kind: str, key: str, data: dict):
        path = self.record_path(kind, key)
        temporary = path.with_suffix(".tmp")
        temporary.write_text(json.dumps(data, indent=2) + "\n")
        temporary.chmod(0o600)
        temporary.replace(path)

    def original(self, source: dict) -> Path:
        if source.get("revoked"):
            raise ClipError("Original authorization has been revoked")
        path = (self.originals / str(source["relative_path"])).resolve(strict=True)
        if not path.is_relative_to(self.originals) or not path.is_file():
            raise ClipError("Original must remain inside the configured originals directory")
        if not 0 < path.stat().st_size <= MAX_SOURCE_BYTES:
            raise ClipError("Original exceeds the 10 GiB input limit")
        if "mtime_ns" in source and (
            path.stat().st_mtime_ns != source["mtime_ns"] or path.stat().st_size != source["bytes"]
        ):
            raise ClipError("Original changed after registration")
        return path

    def register(
        self, video_id: str, owner_id: str, source_path: Path, rights_note: str, *, timeline_aligned: bool
    ) -> dict:
        if not timeline_aligned:
            raise ClipError("Confirm that original timestamps align with the archive recording")
        video_id, owner_id = str(UUID(video_id)), str(UUID(owner_id))
        if not 10 <= len(rights_note.strip()) <= 2000:
            raise ClipError("Record a specific authorization basis (10–2000 characters)")
        path = source_path.resolve(strict=True)
        if not path.is_relative_to(self.originals):
            raise ClipError("Original is outside the configured originals directory")
        source = {
            "video_id": video_id,
            "owner_id": owner_id,
            "relative_path": str(path.relative_to(self.originals)),
            "rights_note": rights_note.strip(),
            "registered_at": time.time(),
            "revoked": False,
            "timeline_aligned": True,
        }
        self.original(source)
        source.update(probe(path))
        source["sha256"] = digest(path)
        source["bytes"] = path.stat().st_size
        source["mtime_ns"] = path.stat().st_mtime_ns
        with self.lock():
            if self.record_path("sources", video_id).exists():
                raise ClipError(
                    "Video already has a source record; use a new video ID or review/revoke the existing registration"
                )
            self.save("sources", video_id, source)
        return source

    def enqueue(self, video_id: str, owner_id: str, start_ms: int, end_ms: int) -> dict:
        owner_id = str(UUID(owner_id))
        if (
            type(start_ms) is not int
            or type(end_ms) is not int
            or start_ms < 0
            or not 0 < end_ms - start_ms <= MAX_DURATION_MS
        ):
            raise ClipError("Select between 1 millisecond and 120 seconds")
        with self.lock():
            source = self.load("sources", video_id)
            if source["owner_id"] != owner_id:
                raise ClipError("Only the registered original owner may request this export")
            self.original(source)
            if end_ms > source["duration_ms"]:
                raise ClipError("Selection ends after the authorized original")
            active: list[dict] = [json.loads(p.read_text()) for p in (self.spool / "jobs").glob("*.json")]
            for previous in active:
                if (
                    previous["owner_id"] == owner_id
                    and previous["video_id"] == str(UUID(video_id))
                    and previous["source_sha256"] == source["sha256"]
                    and previous["start_ms"] == start_ms
                    and previous["end_ms"] == end_ms
                    and previous["status"] in ("queued", "running", "completed")
                    and previous["expires_at"] > time.time()
                ):
                    return previous
            if sum(j["expires_at"] > time.time() for j in active) >= 20:
                raise ClipError("Local export capacity reached; clean up expired exports before retrying")
            now = time.time()
            job = {
                "id": str(uuid4()),
                "video_id": str(UUID(video_id)),
                "owner_id": owner_id,
                "source_sha256": source["sha256"],
                "start_ms": start_ms,
                "end_ms": end_ms,
                "status": "queued",
                "created_at": now,
                "expires_at": now + TTL_SECONDS,
            }
            self.save("jobs", job["id"], job)
            return job

    def status(self, job_id: str, owner_id: str) -> dict:
        job = self.load("jobs", job_id)
        if job["owner_id"] != str(UUID(owner_id)):
            raise ClipError("Clip or authorized original not found")
        self.original(self.load("sources", job["video_id"]))
        if job["expires_at"] <= time.time():
            return {**job, "status": "expired"}
        return job

    def output(self, job_id: str, owner_id: str) -> Path:
        job = self.status(job_id, owner_id)
        if job["status"] != "completed":
            raise ClipError("Clip is not complete or has expired")
        path = self.spool / "jobs" / f"{UUID(job_id)}.mp4"
        if not path.is_file() or digest(path) != job["output_sha256"]:
            raise ClipError("Clip output is missing or failed integrity verification")
        return path

    def run(self, job_id: str) -> dict:
        # One renderer per spool. A crashed/interrupted run is never silently retried.
        with self.lock():
            job = self.load("jobs", job_id)
            if job["status"] != "queued" or job["expires_at"] <= time.time():
                raise ClipError("Only an unexpired queued export can run")
            job["status"] = "running"
            self.save("jobs", job_id, job)
            output = self.spool / "jobs" / f"{UUID(job_id)}.mp4"
            partial = output.with_suffix(".partial.mp4")
            try:
                source = self.load("sources", job["video_id"])
                original = self.original(source)
                if digest(original) != job["source_sha256"] or source["sha256"] != job["source_sha256"]:
                    raise ClipError("Original changed after registration")
                if shutil.disk_usage(self.spool).free < 2 * MAX_OUTPUT_BYTES:
                    raise ClipError("Insufficient spool space")
                duration = (job["end_ms"] - job["start_ms"]) / 1000
                subprocess.run(
                    [
                        "ffmpeg",
                        "-nostdin",
                        "-hide_banner",
                        "-loglevel",
                        "error",
                        "-y",
                        "-protocol_whitelist",
                        "file,pipe",
                        "-f",
                        source["format"],
                        "-ss",
                        str(job["start_ms"] / 1000),
                        "-i",
                        str(original),
                        "-t",
                        str(duration),
                        "-map",
                        "0:v:0",
                        "-map",
                        "0:a:0?",
                        "-map_metadata",
                        "-1",
                        "-map_chapters",
                        "-1",
                        "-vf",
                        "scale=1280:720:force_original_aspect_ratio=decrease:force_divisible_by=2",
                        "-c:v",
                        "libx264",
                        "-preset",
                        "veryfast",
                        "-crf",
                        "23",
                        "-threads",
                        "2",
                        "-c:a",
                        "aac",
                        "-b:a",
                        "128k",
                        "-movflags",
                        "+faststart",
                        "-fs",
                        str(MAX_OUTPUT_BYTES),
                        str(partial),
                    ],
                    check=True,
                    capture_output=True,
                    timeout=180,
                )
                if (
                    partial.stat().st_size > MAX_OUTPUT_BYTES
                    or abs(probe(partial)["duration_ms"] - round(duration * 1000)) > 250
                ):
                    raise ClipError("Rendered output failed size/duration checks")
                if digest(original) != job["source_sha256"]:
                    raise ClipError("Original changed while rendering")
                partial.chmod(0o600)
                partial.replace(output)
                job.update(status="completed", output_sha256=digest(output), output_bytes=output.stat().st_size)
            except (OSError, ValueError, subprocess.SubprocessError, KeyboardInterrupt) as exc:
                partial.unlink(missing_ok=True)
                output.unlink(missing_ok=True)
                job.update(
                    status="failed",
                    error=(
                        str(exc)
                        if isinstance(exc, ClipError)
                        else "Renderer failed or was interrupted; inspect the original and worker environment"
                    ),
                )
                self.save("jobs", job_id, job)
                if isinstance(exc, KeyboardInterrupt):
                    raise
                return job
            self.save("jobs", job_id, job)
            return job

    def revoke(self, video_id: str):
        with self.lock():
            source = self.load("sources", video_id)
            source["revoked"] = True
            self.save("sources", video_id, source)
            for path in (self.spool / "jobs").glob("*.json"):
                job = json.loads(path.read_text())
                if job["video_id"] == str(UUID(video_id)):
                    path.with_suffix(".mp4").unlink(missing_ok=True)
                    path.with_suffix(".partial.mp4").unlink(missing_ok=True)
                    job["status"] = "revoked"
                    self.save("jobs", job["id"], job)
        return {"video_id": str(UUID(video_id)), "revoked": True}

    def cleanup(self, apply: bool = False) -> dict:
        removed = []
        with self.lock():
            for path in (self.spool / "jobs").glob("*.json"):
                job = json.loads(path.read_text())
                if job["expires_at"] <= time.time() or job["status"] in ("failed", "revoked"):
                    removed.append(job["id"])
                    if apply:
                        path.with_suffix(".mp4").unlink(missing_ok=True)
                        path.with_suffix(".partial.mp4").unlink(missing_ok=True)
                        path.unlink()
        return {"apply": apply, "jobs": removed}
