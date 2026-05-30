# Architecture Refactor Baseline

Date: 2026-05-29

## Git Status

```text
 M .env.example
 M Dockerfile.cuda
 M alembic/versions/003_transcript_cleanup.py
 M app/crud.py
 M app/routes/jobs.py
 M app/routes/videos.py
 M app/schemas.py
 M app/settings.py
 M docs/DOCKER_VARIANTS.md
 M docs/youtube-ingestion-setup.md
 M frontend/.env.example
 M frontend/package-lock.json
 M frontend/src/routes/SearchPage.tsx
 M frontend/src/routes/VideoPage.tsx
 M frontend/src/services/api.ts
 M frontend/src/tests/AdminDashboard.test.tsx
 M frontend/src/types/api.ts
 M frontend/vite.config.ts
 M requirements.txt
 M sql/schema.sql
 M tests/worker/test_diarize.py
 M worker/audio.py
 M worker/diarize.py
 M worker/loop.py
 M worker/pipeline.py
 M worker/youtube_captions.py
 M worker/youtube_resilience.py
 M worker/ytdlp_client_utils.py
?? alembic/versions/20260529_0315_add_diarization_state.py
?? alembic/versions/20260529_0425_add_caption_ingest_state.py
?? docker-compose.gtx1080.yml
?? docs/gtx-1080-core.md
?? docs/superpowers/
?? worker/diarization_loop.py
```

## Runtime Status

```text
NAME                                     IMAGE                                                                     COMMAND                  SERVICE              CREATED        STATUS                    PORTS
transcript-create-api-1                  sha256:463c2676222d51d0ebb976f5039b04f9fb673d8833a0b5f2f3d23f7019d93a0c   "/opt/nvidia/nvidia_…"   api                  12 hours ago   Up 12 hours (healthy)     0.0.0.0:41177->8000/tcp, [::]:41177->8000/tcp
transcript-create-diarization-worker-1   sha256:c8b27a06a89e20eab2a98426920355cc3e83096fa4ed488f41a71d35ce22643b   "/opt/nvidia/nvidia_…"   diarization-worker   15 hours ago   Up 15 hours (unhealthy)   8000/tcp
transcript-create-worker-1               transcript-create:gtx1080                                                 "/opt/nvidia/nvidia_…"   worker               10 hours ago   Up 10 hours (unhealthy)   8000/tcp
```

## Checks

- `rtk mypy app worker`: PASS
- `python3 -m compileall -q app worker alembic`: PASS
- `rtk npm run build` (frontend): PASS
- `rtk lint` (frontend): PASS

## Notes

- Worker and diarization worker are running but unhealthy.
- Staged batch `channels-20260529-core` must remain caption-first.
- No baseline command failures were encountered.

## Final Architecture Verification

Date: 2026-05-29

### Checks

- `rtk mypy app worker`: PASS
- `python3 -m compileall -q app worker alembic tests scripts`: PASS
- `docker compose -f docker-compose.yml -f docker-compose.gtx1080.yml config --quiet`: PASS
- `rtk npm run build` from `frontend/`: PASS
- `rtk lint` from `frontend/`: PASS
- `rtk vitest src/tests/searchTranscript.matches.test.ts src/tests/entitlements.policy.test.ts src/tests/ExportMenu.test.tsx` from `frontend/`: PASS (14), FAIL (0)
- `scripts/compare_schema_contract.py` with the same local DB on both sides inside the API container: PASS (`Schema contract matches`)

### Runtime observations

- API, DB, and Redis are healthy in Docker Compose.
- Worker container is running but reports `unhealthy` via Compose health check.
- Worker logs show staged batch `channels-20260529-core` reached caption-ready state and native transcription is now processing videos.
- Staged batch state query returned only terminal caption ingest states (`completed`, `unavailable`, `failed`), with native video states including `pending`, `transcoding`, and `completed`; this is consistent with the caption-first gate releasing native transcription after caption ingest became terminal.

### Known verification limitations

- Backend `rtk pytest ...` remains unreliable in this environment and often reports `No tests collected`.
- Host Python cannot run `scripts/compare_schema_contract.py` because `psycopg` is not installed; the script was validated via compile checks and by running inside the API image with `scripts/` mounted.
