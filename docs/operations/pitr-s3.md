# S3-Compatible PITR Runbook

This is an opt-in PostgreSQL physical-backup/WAL archive configuration. It does
not change the normal Compose stack. Logical `pg_dump` files are useful, but
they are **not** PITR base backups.

## Configuration and permissions

Set these credential keys in the deployment environment: `WALG_S3_PREFIX`,
`AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, and `AWS_ENDPOINT`. `AWS_REGION`
defaults to `auto`; set `WALG_RETAIN_FULL` to the desired full-backup count.

Use `WALG_S3_PREFIX=s3://<bucket>/<prefix>` with a dedicated, non-empty prefix.
For Cloudflare R2, use
`AWS_ENDPOINT=https://<account-id>.r2.cloudflarestorage.com` and region `auto`.
For this host's MinIO deployment, use `AWS_ENDPOINT=http://minio:9000`, region
`us-east-1`, and attach the database and backup containers to the external
`dev` network. Do not put credentials in the prefix or endpoint. Credentials
must be limited to the PITR bucket and allow object list, get, put, and delete;
retention requires delete permission.

The local MinIO data directory is on a separate physical disk from PostgreSQL,
which protects against loss of the primary database disk. It does not protect
against complete host/site loss; replicate the bucket off-host for that threat.

## Enablement and preflight

1. Treat PITR enablement or a PITR configuration change as a reviewed immutable
   candidate. During a controlled deployment window, run strict
   `scripts/compose_prod.sh preflight`, then deploy
   that approved candidate with `scripts/compose_prod.sh deploy`. The wrapper
   clears inherited shell variables before loading `.env.prod`, preventing stale
   exported credentials or callback URLs from overriding production configuration.
   Confirm all four required variables are present, the bucket/prefix is unique,
   credentials have the minimum permissions above, and R2 is reachable. Do not
   enable `archive_mode` in the normal Compose configuration.
2. After the controlled deployment, wait for `pg_isready` and check database
   logs for archive errors. Do not use raw state-changing Compose commands.
3. Take the first base backup immediately; do not wait for Sunday:
   `scripts/compose_prod.sh maintenance pitr-base-backup --approved`.
   Then force an archive cycle:
   `scripts/compose_prod.sh maintenance pitr-switch-wal --approved`.
   Both named actions run strict release preflight first; arbitrary production
   `exec` passthrough remains disabled.
4. Validate archiving with
   `scripts/compose_prod.sh maintenance pitr-archive-status --approved` and
   validate the base backup with
   `scripts/compose_prod.sh maintenance pitr-list-backups --approved`.
   Both are fixed read-only actions that run strict release preflight first;
   arbitrary production `exec` remains disabled. Investigate any failed archive
   count or missing backup before relying on PITR.

## Restore rehearsal

Regularly restore into a disposable, empty PGDATA directory on an isolated
staging host/container with a staging-only bucket/prefix. Use `wal-g
backup-fetch <empty-pgdata> LATEST`, configure PostgreSQL recovery to call
`wal-g wal-fetch "%f" "%p"`, set an explicit recovery target when testing
point-in-time recovery, then start that isolated instance and validate
application data. Record the selected WAL-G base backup, WAL replay, timing,
and integrity result before rehearsing additive migrations. Never run
`backup-fetch` over live PGDATA and never rehearse against the production
database. A logical restore is supplemental evidence, not PITR proof.

## Retention and rollback

The weekly job runs `backup-push` and, only when it succeeds, `wal-g delete
retain FULL ${WALG_RETAIN_FULL:-5} --confirm`. Set the count to cover the
required recovery window; deleting old full backups also makes their dependent
WAL history unrecoverable. Review R2 lifecycle rules so they do not expire WALs
needed by retained backups.

The guarded production stack has no ad hoc in-place PITR-disable command. Treat
disablement as a reviewed release change: first verify a recent logical backup
and the required restore rehearsal, revise the authoritative helper/overlay in
source, pass the release gates, and deploy the resulting immutable candidate.
Do not construct a partial Compose command that omits the PITR overlay. Keep R2
objects until the approved retention period ends; never remove archive data
merely because archiving has been disabled.
