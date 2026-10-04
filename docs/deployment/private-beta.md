# Private-beta deployment runbook

**Status:** operator-pending release gate (2026-07-23).

This runbook is fail closed: do not begin the next gate until the preceding gate
has recorded evidence. The application intentionally keeps archive reads public;
invite-only access is enforced by external ingress, not by a new application
route.

## Ordered release gates

1. **Freeze and publish candidate evidence.** Record the source commit. On its
   protected `release/v*-rc.*` or `release/v*-beta.*` branch, dispatch the Gitea
   release workflow as the configured release operator and require verification,
   browser, exact-digest scan, signing/attestation, and evidence-artifact success.
   Only then create the matching RC/beta tag. Download the Gitea prerelease's
   `release-images.json`, run `scripts/compose_prod.sh preflight`, and record the
   exact approved image digests. Do not deploy tags, `latest`, Watchtower, or any
   automatic-update service.
2. **Rotate and scan.** Rotate existing local credential and cookie values,
   including `.env.prod` and `cookies.txt`, then complete the approved secret
   scan. Record an attestation of completion and rotation time only—never values,
   paths containing values, or scan output. **Operator pending.**
3. **Prove access control.** Configure the external management ingress for the
   approved invite cohort. Inspect firewall rules and listeners to prove API and
   archive frontend host bindings cannot reach the public internet around that ingress;
   perform a remote negative probe without an invite. Retain private evidence
   without publishing addresses, rules, or credentials. A successful direct host
   API or frontend request blocks release. **Operator pending.**
4. **Verify candidate.** Record passing `make verify` for the frozen core commit
   and the archive frontend's own desktop and mobile browser evidence. Core no
   longer produces browser artifacts. Any S0/S1 blocks release.
5. **Rehearse on staging.** Use a separate staging host. Fixed names, ports,
   networks, and bind paths make co-location with production unsafe. Use empty,
   isolated PostgreSQL and media storage and a staging-only WAL-G bucket/prefix;
   never point staging at production storage. **Operator pending.**
6. **Prove recovery and migration.** First verify a current recovery point.
   Start PostgreSQL only, restore the WAL-G base backup and replay WAL into empty
   storage, validate integrity and timing, then rehearse additive migrations.
   Before application writers start, select an approved timestamped media backup
   at `/backups/media/<timestamp>` and its matching generated manifest
   `/backups/media/checksums_<timestamp>.sha256`. Verify the source with
   `sha256sum -c /backups/media/checksums_<timestamp>.sha256`, then restore it
   only into an empty, isolated staging media target (never production), for
   example: `rsync -a --delete /backups/media/<timestamp>/ <staging-media>/`.
   For both source and target, record `find <path> -type f | wc -l` and
   `find <path> -type f -printf '%s\n' | awk '{total += $1} END {print total + 0}'`;
   their file counts and file-byte totals must match. Record the
   source timestamp and manifest identity, the checksum result, those totals,
   and the result of
   `rsync -a --delete --checksum --dry-run /backups/media/<timestamp>/ <staging-media>/`;
   the dry run must report no differences. Start application writers only after
   this media evidence and the migration head are recorded. A logical `pg_dump`
   restore alone does not satisfy this PITR gate. Rehearse any maintenance-only
   session/analytics boundary separately under
   [Migrations](../MIGRATIONS.md). **Operator pending.**
7. **Deploy immutable release.** Re-run preflight and deploy the recorded
   digests through the guarded helper. Confirm Watchtower and automatic updates
   are absent/disabled before deployment. If strict preflight reports containers
   left by a previously enabled `full` or `diarization` profile, run only
   `scripts/compose_prod.sh maintenance retire-disabled-profiles --approved`,
   then re-run strict preflight. That action retires the fixed disabled-profile
   service set; it is not arbitrary service passthrough. **Operator pending.**
8. **Operational smoke.** Verify archive frontend and API health; CSP and cache headers;
   OAuth; search fallback and lag; ingestion leases and retries; retention;
   backup recency; and alert delivery. On the target host, the default CUDA
   transcription image must pass import, GPU-visibility, and bounded-transcription
   smoke tests. The ML diarization image/profile is optional and CPU-only; if
   used, it must separately pass import and bounded allow-listed one-off
   diarization smoke (it must not require GPU visibility).
   **Operator pending.**
9. **Pass moderated entry.** Complete the moderated gate in the
   [testing protocol](../user-testing/private-beta.md) and retain its consent,
   accessibility, task, and defect evidence. Do not require beta-observation
   evidence before the beta has opened. **Operator pending.**
10. **Decide beta entry.** The named owner records **open invite beta**,
    **hold**, or **roll-forward**. Opening the private beta requires gates 1–9,
    zero open S0/S1, and the completed moderated gate. It does not authorize a
    public launch. **Operator pending.**

## Beta operation and exit

After beta entry, follow the daily triage, named health/search-lag/worker-lease/
backup checks, seven-consecutive-stable-day rule, restore-evidence requirement,
and reset conditions in the [testing protocol](../user-testing/private-beta.md).
Retain the beta observation window and defect burn-down in the evidence packet.

When those exit criteria pass, the named owner records **exit beta**,
**extend**, or **hold**. Public launch remains a separate, explicit decision;
beta exit does not publish or ungate the archive.

## Rollback boundaries

An ordinary additive rollout may restore previously recorded compatible
application digests; keep additive migrations compatible through that rollback.
After either the analytics credential-scrub/session-rotation boundary or the
hash-only session migration boundary, old images are forbidden: recovery is
roll-forward only. See [Migrations](../MIGRATIONS.md) and
[production readiness](../operations/production-readiness.md).

## Evidence packet

The release owner keeps a restricted packet containing:

- frozen commit, manifest, and exact image digests;
- verification run IDs and browser artifacts;
- secret-rotation and secret-scan attestation without values;
- staging host separation, WAL-G base-backup plus WAL-replay timings, approved
  timestamped media-backup and matching-manifest identities, source checksum,
  isolated empty-media restore, target file-count/byte-total and checksum-rsync
  dry-run results, and migration head before writers;
- ingress/firewall/listener inspection and remote-negative-probe proof, without
  sensitive network detail in public artifacts;
- health screenshots or query results for headers, OAuth, search lag/fallback,
  leases/retries, retention, backup recency, alerts, and CUDA smokes;
- moderated-session results and beta-entry decision, followed after entry by
  the defect burn-down, beta observation window, stable-day record, and
  accepted S2/S3 issues with owner/date; and
- decision, accountable owner, timestamp, and all remaining operator-pending
  gates.

Missing evidence means the associated gate is pending, not passed.
