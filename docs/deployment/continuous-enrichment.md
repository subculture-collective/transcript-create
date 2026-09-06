# Continuous review-only enrichment

Goal: prioritize newly transcript-ready videos, backfill newest-to-oldest, and
retry technical rejections without overwriting editorial decisions.

The user authorized implementation, publication, deployment, and continuous paid
processing on 2026-09-06, conditional on passing the safeguards below.

## Contract

- DeepSeek V4 Pro, balanced windows of at most 90 minutes, candidate-only output.
- Durable jobs distinguish initial backfill, later arrivals, delayed retries,
  completed work, and parked failures. New arrivals precede untouched backfill;
  due retries follow untouched work. Priority changes between videos only.
- At most three paid/technical attempts per video/model/prompt, including known
  historical failed attempts. Retry after 15 minutes, then one hour.
- Editorially rejected, edited, published, or hidden work is never automatically
  retried. Legacy completed runs rejected by automated quality checks require an
  explicit provenance-preserving supersession path.
- One database-fenced queue owner; no simultaneous canary and daemon. Interrupted
  or uncertain paid attempts pause for inspection rather than blind replay.
- Provider credit exhaustion and systemic errors persist a pause across restarts.
  A single video quality failure is delayed/parked, not a whole-backfill failure.
  Three consecutive failed jobs also pause, including failures before a provider
  attempt record exists; the existing rolling failure-rate breaker still applies.
- All per-video acceptance checks run before committing candidates. Failures
  retain measured usage, with no partial candidate writes.
- Production remains disabled during implementation and deployment validation.
  Activation is a distinct recorded operation using the qualified API digest.
- Activation settings: 30-second idle polling, three attempts per job, $1/video,
  10,000 attempts/$250 per rolling day. Provider/key credit ceilings still apply;
  these elevated application ceilings are not a promise of available credit.

## Acceptance and verification

Exercise real PostgreSQL priority, retries, concurrency fencing, restart/pause
behavior, and editorial protection. Exercise zero-category/evidence/coverage and
stored-count failures with rollback. Run focused tests, static checks, full local
verification, PR/main CI, and immutable image qualification. Before production
deployment obtain a fresh WAL-G backup and rollback package; validate migrations,
health and protected-row evidence. Enable only after all gates pass, then observe
actual paid completions and verify candidate-only output and queue ordering.

Open questions: none for the above contract. Implementation and production
activation evidence must be recorded before calling this work complete.

## Operations

The release overlay defaults to `--once` / restart `no`. Enabling continuous
processing requires `ARCHIVE_ENRICHMENT_ENABLED=true`, publication `false`,
`ARCHIVE_ENRICHMENT_QUEUE_MODE=--continuous`, and
`ARCHIVE_ENRICHMENT_QUEUE_RESTART_POLICY=unless-stopped` together. Preflight also
requires the pinned model, 90-minute window setting, and $1 per-video ceiling.
Do not activate by starting the default one-shot service repeatedly.

Read state without claiming work:

```sh
docker exec hasanara-api python3 /app/scripts/run_archive_enrichment_queue.py --once --queue-status
```

To requeue a recorded technical rejection, first gracefully stop the continuous
worker. Then execute the packaged CLI with `--once --requeue-run <run_uuid>`.
This makes no provider request. It snapshots original chapter/LLM-assignment
rows in `archive_enrichment_supersessions` before removing those verified,
unedited candidates from active tables. Existing labels and extraction runs
remain unchanged. It refuses editorial feedback, non-candidate or edited rows,
other runs' rows, dependent non-LLM assignments, and exhausted attempt budgets.
Snapshots retain original IDs and timestamps for controlled recovery. Never
delete or reset the queue ledger to obtain more attempts.

Credit exhaustion and the systemic failure breaker persist a pause. After
addressing the cause and stopping the worker, `--once --resume-queue` clears the
pause without making a provider request. It refuses any unresolved running job
or extraction. Inspect and reconcile interrupted attempts and measured usage
before resuming; do not blindly cancel them. Restart the same pinned service
only after that check. `--once --queue-status` remains available while paused.

SIGTERM/SIGINT request a graceful stop after the current video. Compose permits
20 minutes for completion. A forced kill or database-connection loss leaves a
durable uncertain/running record, causing a pause on restart instead of replay.
