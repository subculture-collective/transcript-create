# Continuous review-only enrichment

Goal: prioritize newly transcript-ready videos, backfill newest-to-oldest, and
retry technical rejections without overwriting editorial decisions.

The user authorized implementation, publication, deployment, and continuous paid
processing on 2026-09-06, conditional on passing the safeguards below.

September 7 amendment: the explicitly opted-in [PR28 approval policy](enrichment-approval-cutover.md)
adds automatic publication only after all quality and editorial checks pass.
Review-only behavior remains the default; canaries always disable auto-approval.
The amendment does not authorize clearing a provider/failure pause.

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
  Three consecutive unhandled failed jobs also pause, including failures before
  a provider attempt record exists. The rolling systemic failure-rate breaker
  excludes only exact recognized quality rejections owned by a durable retry job:
  chapter evidence overlap/unsupported evidence, no sustained categories, and
  the 30-second publication minimum. These rejections remain failed runs, consume
  the same three-attempt allowance and measured/reserved spending, and eventually
  park. They are removed from both numerator and denominator before selecting
  the systemic sample, so they cannot dilute unknown or provider failures.
  One-shot runs retain the strict failure sample. Existing pauses require explicit
  verified recovery; deployment does not clear them or reset any attempt history.
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

Provider routing: leave `ARCHIVE_ENRICHMENT_OPENROUTER_PROVIDER_ONLY=` empty
to let OpenRouter select and fail over between providers of the same DeepSeek
V4 Pro model. A nonempty provider slug retains explicit pinning without fallback.
Strict JSON schema, required parameters and denied data collection remain
mandatory. Provider pricing can vary; per-video and daily cost breakers, including
unknown-billing reservations, still apply. Provider fallback does not authorize
model fallback, application-level replay of uncertain requests, or pause resets.
Explicit rate-limit HTTP 429 or rate-limit-message HTTP
413 responses retry at most twice with 15/30-second backoff and Retry-After
support. A requested wait over 60 seconds stops instead of retrying early.
Explicit HTTP 502/503 and recognized response-body 502/503 failures enter a
durable `provider_cooldown`. No other video starts during that cooldown. At the
existing retry deadline (15 minutes on the first attempt, one hour on later
attempts), the same eligible video receives one recovery probe. This is a normal
counted extraction with all eligibility, owner, attempt, failure-rate and cost
guards still active. Success clears only the cooldown; failure leaves a durable
operator-reviewed pause. An interrupted probe is never automatically replayed.
No recovery checkpoint is inserted and no failure history is reset automatically.

Durably accounted uncertain transport outcomes quarantine only the affected video:
the job becomes `parked` with reason `transport_uncertain_quarantined`, retains its
attempt count and failed run, and is not automatically replayed. This requires
the exact stored transport error, unreported usage, a positive cost reservation,
and no chapter or LLM assignment rows. Ordinary requeue refuses uncertain runs
and other runs for the same video until separately reviewed reconciliation.
Unrelated work continues, but quarantined failures remain in both spending and
systemic failure-rate accounting; three consecutive unhandled/quarantined failures
still pause the queue. Uncertain failures during an existing recovery probe retain
the global pause. Missing accounting or conflicting output also retains the pause.

Unrecognized errors, schema incompatibility,
authentication/credit failures and exhausted rate retries retain hard-stop
behavior. Measured completed-window usage survives failures; partial candidates
never persist. Sanitized `provider_failure` metrics retain the error code,
allowlisted error type, safe generation ID when present and `usage_reported`.
Missing billing information is not confirmed zero: a separate
`cost_reservation_usd` reserves one configured per-video budget in addition to
known measured usage. Daily cost guards include both, reported separately as
`recorded_cost_usd_24h` and `reserved_cost_usd_24h`. Reservations are conservative
local guardrail accounting, not additional provider charges.

Existing `provider_failure` pauses are intentionally not reclassified or resumed
on deployment. Diagnose and explicitly recover those under the procedure below.
For the approved automatic-routing rollout, explicitly clear the historical
Almaz `alibaba` override after image qualification; changing the code default
alone does not remove an existing environment pin. Verify the actual request
omits `provider.only` and enables `allow_fallbacks`, while retaining the model,
schema, privacy and cost constraints. Record bounded recovery before resuming.

After operator investigation and stopping the worker, explicit `--resume-queue`
now records an append-only `archive_enrichment_recoveries` checkpoint with the
previous pause reason. Rolling failure samples and consecutive-failure checks
start at that recovery boundary. Original failed runs, retry attempts and
24-hour attempt/cost accounting are unchanged. Calling resume on an unpaused
queue is refused. This is an explicit recovery operation, not an automatic
reset or a way to evade daily spending limits.

Input preflight now uses the selected/exported transcript and the same balanced
window splitter as generation before a continuous job is claimed. Each window
must contain text, and at least two distinct block starts must span 20% of the
episode. This input floor applies even when a category title/marker could bypass
the ordinary output evidence-spread rule. It avoids paying for effectively empty
inputs without relaxing any output evidence or category requirement.

Known input defects return `input_parked` and retain a durable
`transcript_input:*` reason. No attempt is consumed, no extraction is created,
and existing attempt counts/run references remain intact. Unknown export or
configuration failures are not silently classified as source-data defects.
Exact-video enrichment repeats the preflight before creating an extraction.
Parked input jobs are not automatically replayed; repair the transcript and
explicitly reconcile the job before retrying. This code change does not erase
historical failures, clear the production pause, or bypass the rolling breaker.

For a historical failed run with the exact empty-window error and no provider
usage fields, stop the worker and use `--once --reconcile-input-run <run_uuid>`.
This requires the current transcript to reproduce the defect, pristine review
state, and the run to remain the job's latest inactive attempt. It retains the
failed status, original metrics and attempts; adds an idempotent timestamped
`input_preflight_reconciliation` annotation; and parks the job. Annotated unpaid
input failures no longer enter the provider failure-rate sample. Daily attempts
and cost accounting remain unchanged. Paid/unknown failures cannot be reconciled
this way. Re-evaluate all guardrails before explicit resume.

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
