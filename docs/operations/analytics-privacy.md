# Analytics Privacy and Credential-Removal Runbook

## Data model and access

The application uses the legacy-named `ha_analytics` cookie for first-party usage
analytics. The cookie contains 32 random bytes encoded as unpadded base64url;
it is `HttpOnly`, `SameSite=Lax`, valid for one year, and `Secure` in
production. The database stores only its HMAC-SHA256 digest in
`events.analytics_subject_id`. The HMAC key is `ANALYTICS_HMAC_SECRET`, which
must contain at least 32 UTF-8 bytes and be generated independently from the
login `SESSION_SECRET`. Production startup rejects the placeholders shipped in
the environment and Kubernetes templates. Generate a key with
`openssl rand -hex 32` rather than adapting either placeholder.

Raw events may also contain a nullable `user_id` for authenticated product
operations. Admin-only event routes can read raw events. Daily aggregates are
keyed only by UTC day and event type and contain no user or analytics subject.
Neither the API nor CSV export reads or returns login-session credentials.

Browser producers and backend writers share a fixed event taxonomy:
`search`, `result_click`, `seek`, `favorite_add`, `favorite_remove`,
`video_open`, `export_click`, `export`, and `search_api`. The API rejects
unknown types and persists only bounded identifiers, dates, numbers, and
enumerated format/source fields. Raw queries, titles, arbitrary nested data,
and credential-like properties are discarded before insertion. Historical
unknown types are aggregated only as `other`.

Raw events are retained for 90 days. Compose runs
`scripts/maintain_event_retention.py` every 24 hours, while the Kubernetes and
Helm CronJobs run daily at 03:17 UTC. The compatibility wrapper
`scripts/maintain_event_retention.sh` supports a manual maintenance run. Each
path transactionally adds expired rows to `event_daily_aggregates` before
deleting them. The non-identifying daily aggregates may be retained for
historical reporting.

## Expand and deploy

1. Back up PostgreSQL and verify a restore before changing production.
2. Set a new `ANALYTICS_HMAC_SECRET` in the deployment secret using
   `openssl rand -hex 32`. It must contain at least 32 UTF-8 bytes. Do not reuse
   or derive it from `SESSION_SECRET`.
3. Apply Alembic through revision `20260710_analytics_idx`. The first revision
   adds the nullable subject column, its check, and the aggregate table; the
   child revision builds the subject index concurrently outside the migration
   transaction. On an upgraded database, the nullable legacy compatibility
   column remains.
4. Deploy the token-free API and frontend, then drain every older API pod.
5. Confirm event inserts, admin JSON, and CSV contain no login credential.

## Credential scrub and session rotation

The next step is intentionally disruptive: every login session is invalidated
because historical event rows may contain a still-valid credential. Run it
only after old pods have drained:

```bash
export CONFIRM_ANALYTICS_CREDENTIAL_ROTATION=rotate-all-sessions-and-scrub-event-credentials
bash scripts/finalize_analytics_identity.sh
```

The script takes the same transaction-scoped advisory lock used by scheduled
retention, preserves expired daily counts, clears historical event payloads and
login credentials, normalizes unknown historical event types to `other`,
deletes every login session, and installs a temporary trigger that nulls any
legacy writer's credential. It is guarded, transactional, and safe to retry,
but retrying rotates sessions again.

Verify the boundary without printing credential values:

```sql
SELECT count(*) AS populated_legacy_credentials
FROM events
WHERE session_token IS NOT NULL;

SELECT count(*) AS active_login_sessions FROM sessions;

SELECT tgname
FROM pg_trigger
WHERE tgname = 'events_null_legacy_session_token'
  AND NOT tgisinternal;
```

Both counts must be zero and the trigger must be present.

## Rollback boundary

Before finalization, the additive migration and token-free application can be
rolled back independently. After finalization, the release is roll-forward
only: do not restore an image that writes login credentials to events, and do
not remove the temporary trigger while any such image can run. Session
invalidation and credential scrubbing are deliberately irreversible. A future
contract migration may remove the empty compatibility column only after the
roll-forward window closes; that contract migration is not part of this
release.

Fresh installations use `sql/schema.sql`, which has no compatibility column,
and must not run the one-time finalization script.
