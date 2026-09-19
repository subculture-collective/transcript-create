# Recollect local delivery evidence — September 19, 2026

The first product phase and several later-roadmap foundations are implemented locally on `codex/passage-sharing`. This is not a deployed or fully release-qualified product. Community, AT sharing and original-media clip export remain opt-in. No live account, social post, paid inference, real media acquisition or production mutation was performed.

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

## Final verification after reboot

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

1. **Dependency qualification.** Local Python audit reports five findings across AnyIO 4.14.0, Lightning 2.6.5 and Torch 2.12.1, with reported fixes 4.14.2, 2.6.6 and 2.13.0. Lightning/Torch exceptions expired September 13 and were not renewed. Installed development versions differ from repository constraints and ML image pins; reproduce audits on exact role artifacts, resolve compatible pins and qualify ML behavior before release. Frontend audit returned HTTP 503 maintenance on repeated attempts; known frontend patches are installed, but a clean audit was not established.
2. **AT provider integration.** Test real consent/callback, refresh/revocation, custom-PDS behavior, public record readback and retry ambiguity with an authorized test account. Local site-account linking and remote reply synchronization are not implemented; the standalone sharing account is intentionally independent.
3. **Clip operations.** Qualify the renderer's production sandbox/network boundary, worker scheduling, expiry cleanup, capacity and monitoring. Register only authorized originals with explicit timeline alignment. Registration ownership after account merge/deletion needs operator review. No production worker was deployed.
4. **Managed PDS.** Existing Subcult PDS code was assessed rather than duplicated. Customer domain control, CAR/blobs export validation, email recovery, encrypted off-host backup, isolated restore and authorized migration remain qualification gates; see `managed-pds-boundary.md`.
5. **Release and product validation.** Build exact images, back up the target, apply migration under a reviewed release procedure, verify rollback and real browser journeys. Creator permission, moderation ownership, customer demand and naming remain business decisions. Private/paid communities and alpha protocol Spaces are outside this delivery.

Further local feature work should start from this ledger. Do not treat the dependency audit failure or unperformed provider/production checks as passing because unit tests and builds passed.
