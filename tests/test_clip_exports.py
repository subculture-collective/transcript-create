import shutil
import subprocess
import time
import uuid

import pytest
from sqlalchemy import text

from app.clip_exports import ClipError, ClipStore, probe
from app.main import app
from app.security import require_auth
from app.settings import settings


@pytest.fixture
def clip_store(tmp_path):
    if not shutil.which("ffmpeg") or not shutil.which("ffprobe"):
        pytest.skip("ffmpeg and ffprobe required for synthetic original checks")
    originals = tmp_path / "originals"
    originals.mkdir()
    media = originals / "generated.mp4"
    subprocess.run(
        [
            "ffmpeg",
            "-nostdin",
            "-loglevel",
            "error",
            "-f",
            "lavfi",
            "-i",
            "testsrc2=size=320x240:rate=25",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=440:sample_rate=44100",
            "-t",
            "3",
            "-c:v",
            "libx264",
            "-threads",
            "1",
            "-c:a",
            "aac",
            str(media),
        ],
        check=True,
        timeout=20,
    )
    return ClipStore(tmp_path / "spool", originals), media, str(uuid.uuid4()), str(uuid.uuid4())


def register(fixture):
    store, media, video, owner = fixture
    store.register(
        video, owner, media, "Synthetic test pattern generated for export verification", timeline_aligned=True
    )
    return store, media, video, owner


def test_real_render_owner_integrity_and_expiration(clip_store):
    store, media, video, owner = register(clip_store)
    job = store.enqueue(video, owner, 500, 2500)
    assert store.enqueue(video, owner, 500, 2500)["id"] == job["id"]
    with pytest.raises(ClipError):
        store.status(job["id"], str(uuid.uuid4()))
    completed = store.run(job["id"])
    assert completed["status"] == "completed", completed
    output = store.output(job["id"], owner)
    assert abs(probe(output)["duration_ms"] - 2000) < 100
    assert output.stat().st_mode & 0o077 == 0
    completed["expires_at"] = time.time() - 1
    store.save("jobs", job["id"], completed)
    assert store.status(job["id"], owner)["status"] == "expired"
    with pytest.raises(ClipError):
        store.output(job["id"], owner)
    assert store.cleanup()["jobs"] == [job["id"]]
    assert output.exists()
    store.cleanup(apply=True)
    assert not output.exists()


def test_original_boundaries_and_authorization(clip_store, tmp_path):
    store, media, video, owner = clip_store
    outside = tmp_path / "outside.mp4"
    shutil.copyfile(media, outside)
    with pytest.raises(ClipError):
        store.register(video, owner, outside, "Synthetic source", timeline_aligned=True)
    with pytest.raises(ClipError):
        store.register(video, owner, media, "Synthetic source", timeline_aligned=False)
    register(clip_store)
    for start, end in [(-1, 2), (2, 1), (0, 120001), (0, 4000), (True, 1000)]:
        with pytest.raises(ClipError):
            store.enqueue(video, owner, start, end)
    with pytest.raises(ClipError):
        store.enqueue(video, str(uuid.uuid4()), 0, 1000)
    media.unlink()
    media.symlink_to(outside)
    with pytest.raises(ClipError):
        store.enqueue(video, owner, 0, 1000)


def test_changed_original_and_revocation_fail_closed(clip_store):
    store, media, video, owner = register(clip_store)
    job = store.enqueue(video, owner, 0, 1000)
    with media.open("ab") as stream:
        stream.write(b"changed")
    assert store.run(job["id"])["status"] == "failed"
    assert not (store.spool / "jobs" / f"{job['id']}.mp4").exists()
    store.revoke(video)
    with pytest.raises(ClipError):
        store.enqueue(video, owner, 0, 1000)


def test_render_timeout_cleans_partial_output(clip_store, monkeypatch):
    store, media, video, owner = register(clip_store)
    job = store.enqueue(video, owner, 0, 1000)

    def timeout(*args, **kwargs):
        (store.spool / "jobs" / f"{job['id']}.partial.mp4").write_bytes(b"partial")
        raise subprocess.TimeoutExpired("ffmpeg", 180)

    monkeypatch.setattr(subprocess, "run", timeout)
    assert store.run(job["id"])["status"] == "failed"
    assert not list((store.spool / "jobs").glob("*.mp4"))


def test_clip_api_is_owner_only_and_honors_source_deletion(client, db_session, clip_store, monkeypatch):
    store, media, video, owner = register(clip_store)
    monkeypatch.setattr(settings, "CLIP_EXPORTS_ENABLED", True)
    monkeypatch.setattr(settings, "CLIP_ORIGINALS_ROOT", str(store.originals))
    monkeypatch.setattr(settings, "CLIP_SPOOL_DIR", str(store.spool))
    db_session.execute(text("INSERT INTO users(id,name) VALUES (:id,'Original owner')"), {"id": owner})
    job_id = uuid.uuid4()
    db_session.execute(
        text("INSERT INTO jobs(id,kind,input_url) VALUES (:id,'single','https://example.invalid')"), {"id": job_id}
    )
    db_session.execute(
        text("INSERT INTO videos(id,job_id,youtube_id) VALUES (:id,:job,:youtube)"),
        {"id": video, "job": job_id, "youtube": video},
    )
    assert client.post("/clips", json={"video_id": video, "start_ms": 0, "end_ms": 1000}).status_code == 401
    app.dependency_overrides[require_auth] = lambda: {"id": owner, "role": "user"}
    try:
        response = client.post("/clips", json={"video_id": video, "start_ms": 0, "end_ms": 1000})
        assert response.status_code == 202, response.text
        job = response.json()
        assert "owner_id" not in job and "relative_path" not in job
        assert client.get(f"/clips/{job['id']}/download").status_code == 404
        store.run(job["id"])
        download = client.get(f"/clips/{job['id']}/download")
        assert download.status_code == 200
        assert download.headers["content-type"] == "video/mp4"
        assert "no-store" in download.headers["cache-control"]
        app.dependency_overrides[require_auth] = lambda: {"id": str(uuid.uuid4())}
        assert client.get(f"/clips/{job['id']}").status_code == 404
        assert client.get(f"/clips/{job['id']}/download").status_code == 404
        app.dependency_overrides[require_auth] = lambda: {"id": owner, "role": "user"}
        db_session.execute(text("DELETE FROM videos WHERE id=:id"), {"id": video})
        assert client.get(f"/clips/{job['id']}/download").status_code == 404
    finally:
        app.dependency_overrides.pop(require_auth, None)


def test_clip_feature_disabled(client, monkeypatch):
    monkeypatch.setattr(settings, "CLIP_EXPORTS_ENABLED", False)
    assert client.get(f"/clips/{uuid.uuid4()}").status_code == 404
