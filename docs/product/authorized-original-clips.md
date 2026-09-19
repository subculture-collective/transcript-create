# Authorized-original clip exports

Implemented locally, opt-in (`CLIP_EXPORTS_ENABLED=false`). Acquisition remains separate: this code has no remote-media downloader or upload endpoint. Operators register a local creator-authorized original and an owning archive account UUID. A rights note records the operator's declaration, not independent proof of permission. Registration requires confirmation that original timestamps align exactly with the archive recording.

## Operator workflow

Use separate directories for immutable originals and the private spool. The spool must be mode 700; generated media and metadata are mode 600. Registration/renderer commands run as a trusted operator, not as public HTTP inputs.

```bash
python scripts/clip_exports.py --originals /srv/originals --spool /srv/clip-spool register \
  --video-id VIDEO_UUID --owner-id ACCOUNT_UUID --source /srv/originals/recording.mp4 \
  --rights-note 'Creator supplied original under documented export permission …' \
  --confirm-timeline-alignment
python scripts/clip_exports.py --originals /srv/originals --spool /srv/clip-spool run-next
python scripts/clip_exports.py --originals /srv/originals --spool /srv/clip-spool cleanup
python scripts/clip_exports.py --originals /srv/originals --spool /srv/clip-spool cleanup --apply
python scripts/clip_exports.py --originals /srv/originals --spool /srv/clip-spool revoke VIDEO_UUID
```

Configure `CLIP_ORIGINALS_ROOT` and `CLIP_SPOOL_DIR` for the API and the renderer. With the feature enabled, the registered owner requests a range from the passage editor, checks its status and downloads the authenticated MP4. The operator runs one job with `run JOB_UUID` or `run-next`; there is no implicit background process. An operator must arrange regular `run-next` and cleanup invocations before offering this service. These commands have not been installed as production timers.

## Bounds and failure handling

- MP4/MOV/WebM/Matroska originals only, at most 10 GiB and 7680×4320. ffprobe/ffmpeg use a local file/pipe protocol whitelist; caller-controlled URLs and ffmpeg arguments are not accepted.
- Registered source SHA-256, size and mtime are checked; symlinks escaping the originals directory are rejected. Owners and selected time ranges are validated before enqueue. Original and output hashes bind the render to registered bytes.
- At most 120 seconds, 100 MiB output, 180-second ffmpeg timeout, two encoding threads, scaled within 1280×720, one renderer per spool, twenty unexpired jobs. Duplicate requests for an active identical selection reuse the job.
- API registration is intentionally absent. Only the registered owner can request/read/download; administrator role alone does not bypass this authorization. Session/CSRF middleware protects requests. Source deletion blocks API retrieval immediately. Revoking a registration removes generated files. These limits do not stop an already-started download or copies previously obtained by an authorized user.
- Expiry is measured from queue creation, after 24 hours. Expired files cannot be downloaded even before cleanup runs. Physical removal requires `cleanup --apply`. Failed/interrupted renders remove partial outputs. A process killed outside normal exception handling may leave a running job; it is never silently retried and expires into cleanup. Operators must inspect/requeue explicitly.
- Output URLs are authenticated and `private, no-store`. The spool must never be served as static/public storage or included in ordinary archive backups. Account deletion/merge immediately ends access through the old account, but spool metadata is not a database FK: expired files are removed by cleanup and original registrations require operator review after an account merge/deletion. Creator-supplied originals have a separate retention agreement.

The internal utility targets the existing Linux/Python runtime. Deployment still needs a dedicated unprivileged renderer with no network, read-only originals, private writable spool, process/memory/disk limits, monitored scheduling and pinned/patched ffmpeg. No production render service, customer rights clearance, billing or unattended capacity claim is made.

## Verification

Seven focused backend/config tests passed with actual generated test video. Cases cover rendering/duration, wrong owner, escaped paths, incorrect time bounds, changed originals, timeout/partial cleanup, expiry/cleanup, disabled feature and archive-source deletion. Two frontend tests verify queued→download UI and authorization failures.

A real browser requested a 0.500–2.500 second clip through the local API, the one-shot renderer completed it, and the browser downloaded the private MP4. ffprobe measured 1.96 seconds (within one 25 fps frame of the two-second selection), 242,120 bytes. The fixture is a generated test pattern, not a downloaded recording or proof of permission for any creator's media. The fixture's placeholder external player is deliberately unavailable; the rendered original download was the tested journey.

Fresh final-source verification: 1,850 backend tests passed with 82.86% coverage; all migrations, Ruff, Black, isort and mypy baseline passed. The overall verifier remains stopped by the previously documented dependency-audit findings.
