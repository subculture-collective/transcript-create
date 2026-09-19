# Recollect local delivery evidence — September 19, 2026

The first product phase and several later-roadmap foundations are implemented locally on `codex/passage-sharing`. This is not a deployed or fully release-qualified product. Community, AT sharing and original-media clip export remain opt-in. No live account, social post, paid inference, real media acquisition or production mutation was performed.

## Current ML and release qualification follow-up

- `8ab86ac` pins Torch 2.13.0 with TorchAudio 2.11.0 and TorchCodec 0.14.0, updates the combined CUDA role to CUDA 12.6, and corrects the default Compose ROCm index to 7.1. The separate faster-whisper ingest role retains CUDA 12.8.
- Correction to the earlier diagnosis: TorchAudio 2.11 explicitly supports Torch 2.11 and all later releases; a matching TorchAudio 2.13 release is not required. TorchCodec 0.14 likewise supports Torch 2.11 and later. The former compatibility blocker is resolved, not waived.
- `8f3cb01` prevents later installs from downgrading Torch, updates Triton to 3.7.1, removes pip and its vulnerable vendored runtime code after build checks, and excludes every local `.venv*` directory from Docker build contexts. Host environments and evidence remain preserved.
- The exact Lightning 2.6.6 source and checkpoint rejection behavior are checked inside each ML image before accepting a one-package/version VEX correction for Trivy's incorrect fixed-version metadata. All other high/critical application-library findings remain blocking. See [security gate details](../operations/security-gates.md).
- Fresh complete `scripts/verify.sh`, token `recollect-release-final-20260919`, **exit 0**: **1,863 backend tests passed**, **304 frontend tests passed/one existing skip**, **19 browser tests passed**. Disposable database migrations, lint/format, mypy, configured Bandit gate, Python/manifest/npm audits, API contracts, TypeScript/production build and bundle budgets all passed. Log: `output/verification/recollect-20260919/verify-release-final.log`.
- CPU and CUDA ML images built, passed offline synthetic audio decode/resample and pyannote forward checks, and passed the high/critical application-library image gate. CUDA ML was exercised on CPU, matching Almaz's configured optional diarization execution; this is not NVIDIA GPU inference proof.
- API image built, imported the app offline, confirmed runtime pip absent, and passed the same application-library gate.
- ROCm image built and passed the offline synthetic audio/pyannote forward on Kvant's **AMD Radeon RX 7900 XT**, reporting `2.13.0+rocm7.1`. Test used temporary generated audio and random model weights, with container networking disabled and no production data/model downloads. It proves accelerator/runtime operation, not pretrained-model quality or a full archive ingestion job. The ROCm image application-library gate also passed.
- CUDA ingest image built; offline imports of the worker, CTranslate2 4.6.0 and faster-whisper 1.2.0 passed, with runtime pip absent. Its high/critical application-library image gate passed. NVIDIA inference was not executed on Kvant's AMD hardware.
- Frontend release image built; `nginx -t` and offline container HTTP requests for `/`, `/at.html` and `/healthz` passed. Trivy's library gate exits zero but reports no supported language-package inventory in the final Nginx image; npm audit of the actual lockfile is the JavaScript dependency evidence.

Exact local image identities (not signed/published registry release digests):

| Image tag | Docker image identity |
| --- | --- |
| `hasanara-ml-cpu:recollect-qualified` | `sha256:8c8a4b8efc2c7eab1cd40e04a17ab45deb82cfb2dc9305d4f0a1ec94e44e8e4e` |
| `hasanara-ml-cuda:recollect-qualified` | `sha256:9962f9d31a0dfa0f9a09115a471ddd87b21f797e06e336200e420ec1689d28bb` |
| `hasanara-ml-rocm:recollect-qualified` | `sha256:20dea0673a68819aeacd269363b3e5ce232877f7d7e7598e6c028270a0bcb434` |
| `hasanara-api:recollect-qualified` | `sha256:2cd3fce7f570532b6401905aed641b6275e70fdad5605b2df695a6fda5c10e4a` |
| `hasanara-ingest-cuda:recollect-qualified` | `sha256:80af8c83f5fa6c6cd4be511c16d021fd23de9b867ef9403026f0cab8553810c5` |
| `hasanara-frontend:recollect-qualified` | `sha256:cd0dbcee096806725e76f6f5c83d79c890ac19cf5bd06f03691f5e0a07e125e5` |

Current build/scan/smoke logs and image identities are retained under `output/verification/recollect-20260919/` with `qualified` in their names; ROCm GPU evidence is `ml-rocm-gpu-smoke.log`. Earlier failed exploratory logs are not passing evidence. No images were pushed and no services were deployed or restarted.

## Earlier follow-up: reviewed files and audit fixes (superseded below)

The user subsequently authorized reviewing the previously untracked files and fixing the encountered issues. These results supersede the earlier audit status below.

- `d33d229`: committed the corrected deployment quick reference and audio-cleanup utility with disposable-filesystem regression tests. The guide now uses authoritative Gitea/release evidence and removes the hand-written manifest fallback, stale branch example and suppressed migration-log errors. Cleanup rejects extra directories, handles leading dashes, completes discovery before deletion and propagates discovery failures. ShellCheck and Bash syntax passed. No actual audio archive was cleaned.
- Browser screenshots, session traces and synthetic media stay on disk as ignored local artifacts. Existing tracked evidence remains tracked; no artifacts were deleted.
- `5499990`: pinned AnyIO 4.14.2, Lightning 2.6.6 and Setuptools 83.0.0; patched API/ingest image tooling to pip 26.2; removed both expired ML audit suppressions. Fixed the shell gate so failed exception validation cannot be swallowed by `read`. Regression tests exercise that failure status.
- Fresh final backend run (`recollect-ops-final-20260919`): **1,859 tests passed, 82.90% coverage**, Ruff/Black/isort/mypy and configured Bandit gate passed. The full script then correctly failed on the remaining Torch advisory. Disposable services were cleaned up.
- Frontend lockfile audit recovered from the registry outage and reported **zero vulnerabilities**. The repository npm audit wrapper passed. No frontend source behavior changed in this follow-up.
- Constraints inventory audit: **140 packages, zero known vulnerabilities**. This inventory excludes the separately declared ML runtime pins and is not evidence that the whole ML role resolves.
- Built the complete local API image `hasanara-api:recollect-audit-fix`, image identity `sha256:35202f81c7d4ab6f9354c33f62b43b447953c7738f37d7294b317961d0457804`. Application import and `pip check` passed with network disabled. Exported installed inventory: **52 packages, zero known vulnerabilities**. Confirmed exactly one pip/Setuptools/wheel distribution, with versions 26.2/83.0.0/0.47.0. This qualifies Python dependencies, not an OS scan or production deployment.
- Resolved Python 3.10 ingest requirements with the updated constraints: **70 packages, zero known vulnerabilities**. A GPU image build/hardware smoke was not performed in this follow-up.

**Historical ML diagnosis (corrected by the qualification follow-up):** local Torch 2.12.1 remains affected by `GHSA-rrmf-rvhw-rf47`; patched version is 2.13.0. On September 19, official CPU and ROCm 7.1 indexes had a Python 3.11 Linux x86_64 Torch 2.13.0 wheel, CUDA 12.8 did not, and none of those three indexes had TorchAudio 2.13.0. The PyPI TorchAudio 2.13.0 endpoint returned 404. Resolving the repository's Torch 2.11.0 stack with patched Setuptools 83.0.0 fails because Torch requires Setuptools below 82. The local Torch 2.12.1 metadata has the same conflict. No downgrade, ignore renewal or unmatched binary upgrade was used to hide this. A compatible ML runtime upgrade and hardware qualification remain required; see [security gates](../operations/security-gates.md).

Follow-up evidence is under `output/verification/recollect-20260919/`: `backend-ops-final.log`, `npm-audit-followup.json`, `constraints-audit-fixed.json`, `api-image-build.log`, `api-image-freeze.txt`, `api-image-audit.json`, `ingest-candidate-lock.txt`, `ingest-resolution-audit.json`, and `ml-resolution.log`. Earlier failed exploratory logs are retained and are not final passing evidence.

## Source and checkpoints

The initial checkout was fast-forwarded to Almaz's source checkout and Gitea main at `311ddbe3df474b967e46409bc22218c3df49c119`. Both were rechecked after the Kvant reboot and remain at that revision. Runtime image revisions are a separate boundary: the initial deployment inspection found API image revision `45dae4c` and an older web image revision `3ac7305`; syncing source does not establish matching deployed artifacts.

| Commit | Delivered behavior |
| --- | --- |
| `30228f5` | Passage selection, context, bounded preview and reproducible sharing links |
| `65e8ee9` | Public server-rendered passage pages and social preview cards |
| `0605e32` | Creator branding configuration and opt-in community entry points |
| `a3c2e16` | Draft/public updates, passage discussions, replies, moderation, reports and author export |
| `2ff39c1` | Opt-in official AT OAuth SDK and explicit public-post bridge |
| `0257444` | Registered-original clip queue, bounded renderer, expiry and private owner download |
| `05fc1fe` | Vitest/coverage 4.1.11 and transitive filesystem advisory patch |
| `353f01f` | Revision-checked draft/public edits and combined community/archive timeline |

Unrelated untracked deployment instructions and audio-cleanup script were preserved. Browser evidence is retained separately from application commits.

## Earlier verification after reboot

- Fresh `scripts/verify.sh` run with token `recollect-final-20260919`: complete Alembic history applied to disposable PostgreSQL, with disposable Redis/OpenSearch. **1,852 tests passed, 82.90% backend coverage**. Ruff, Black, isort, mypy baseline (zero current errors) and configured Bandit gate passed. The script then stopped at dependency audit; the complete script is not green.
- Final frontend coverage: **304 passed, one existing skip**, 85.96% line coverage. API contract generation comparison, ESLint, Prettier, TypeScript/production build and per-chunk bundle budgets passed. The AT entry remains separate from the archive entry.
- Existing browser regression suite: **19 passed** after reboot. These fixture-backed accessibility/navigation/responsive tests are distinct from the live local API journey below.
- Real browser against a separate synthetic local API database: draft → edit → publish → combined timeline; published text and archive recording persisted; publishing with the timeline open refreshed it immediately. At 390px the document width stayed 390px. Optimistic-edit conflicts and hidden-post edit restrictions are covered by backend and frontend tests.
- Earlier local browser evidence covers source-linked passage selection, actual embedded YouTube stop behavior, publishing/replies and report → hide → restore → resolve. AT verification reached official SDK initialization/provider form only; no external consent or post was performed.
- Earlier synthetic-original clip journey: browser requested 0.500–2.500 seconds, operator ran the queued renderer, and the authenticated browser downloaded a 1.96-second, 242,120-byte MP4. The synthetic artifact survived reboot. This does not prove real creator rights, long-running worker operations or production codec isolation.
- `git diff --check` passed for the final code increment.

Persistent local logs: `output/verification/recollect-20260919/` (`backend-final.log`, `frontend-final-coverage.log`, `frontend-final-build.log`, `frontend-final-bundle.log`, `api-contract.log`, `frontend-format.log`, `browser-regression.log`). Browser screenshots and the synthetic MP4 are under `output/playwright/`. Pre-reboot temporary logs did not survive; the fresh full backend/frontend results above supersede their counts.

The first post-reboot broad run exposed an incorrect YouTube-segment join in the new timeline. It was fixed before the fresh final run above. Browser fixtures were kept in a separate database from backend tests.

## Remaining release gates

1. **Dependency qualification.** The local verification suite and patched manifests now pass; see the current qualification evidence. Exact published registry digests still require the release workflow scans and attestations. OS findings are reported separately from the blocking application-library gate.
2. **AT provider integration.** Test real consent/callback, refresh/revocation, custom-PDS behavior, public record readback and retry ambiguity with an authorized test account. Local site-account linking and remote reply synchronization are not implemented; the standalone sharing account is intentionally independent.
3. **Clip operations.** Qualify the renderer's production sandbox/network boundary, worker scheduling, expiry cleanup, capacity and monitoring. Register only authorized originals with explicit timeline alignment. Registration ownership after account merge/deletion needs operator review. No production worker was deployed.
4. **Managed PDS.** Existing Subcult PDS code was assessed rather than duplicated. Customer domain control, CAR/blobs export validation, email recovery, encrypted off-host backup, isolated restore and authorized migration remain qualification gates; see `managed-pds-boundary.md`.
5. **Release and product validation.** Build exact images, back up the target, apply migration under a reviewed release procedure, verify rollback and real browser journeys. Creator permission, moderation ownership, customer demand and naming remain business decisions. Private/paid communities and alpha protocol Spaces are outside this delivery.

Further local feature work should start from this ledger. Do not treat unperformed provider/production checks as passing because local tests, builds and audits passed.
