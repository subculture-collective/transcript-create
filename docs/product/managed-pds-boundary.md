# Managed PDS: reuse and qualification boundary

Source inspection September 19, 2026: sibling `subcult-pds` checkout at `7316592b3f9d43dd90183742b96f712b7d29a598`, clean. No changes to that repository or live PDS were made. Shell syntax checks passed for its preflight, backup, restore and smoke-test scripts. No backup/restore script was executed: backup stops/restarts a running PDS, and restore mutates its data directory.

## Reusable implementation

- Pinned official PDS image in Compose, invite/admission controls and operator account tooling.
- Preflight checks local prerequisites, directory layout, secret-file location and Compose configuration.
- Backup includes the full data directory and SHA-256 sidecar while the service is stopped.
- Restore requires an explicit flag, verifies checksum, rejects suspicious archive paths and retains pre-restore data.
- Smoke tests inspect PDS health/version, discovery, handle resolution and subscription transport.

The repository's dated deployment ledger records an August 2026 official-image upgrade and successful Patchwork OAuth plus record round trip. That is historical evidence for that deployment/app, not fresh Recollect qualification. The operating guide still documents unset SMTP/password recovery and unencrypted local backups without off-host replication. Those limitations were not rechecked against live secrets or a running host in this increment.

## Product boundary

Use existing accounts at their current provider first. Optional creator PDS hosting must remain separate from archive/community software, AppView indexing, moderation and any staffed service. Neither PDS availability nor a successful OAuth connection guarantees Bluesky indexing, reach, private data, domain ownership or customer exit capability.

A shared PDS lowers per-creator operational overhead but shares failure, upgrade and abuse capacity. A dedicated creator PDS gives clearer resource and backup boundaries at a higher operating cost. Prefer the existing-account bridge for the first release; choose shared or dedicated hosting only for a bounded operator-supported pilot with explicit obligations. Community-wide account hosting remains excluded.

## Required handoff and acceptance contract

| Capability | Required artifact and executable acceptance | Current status |
| --- | --- | --- |
| Domain/identity control | Customer-controlled domain/DNS, handle↔DID resolution, recovery contacts and documented control of PLC recovery/rotation material | Not qualified for a customer |
| Portable public repository | Per-account CAR export, blob inventory and all referenced blobs, hashes, DID document and collection inventory; validate repository/CIDs with official tooling | No authorized customer export performed |
| Local application export | Community author JSON plus archive transcript/metadata exports; document which local moderation/application records do not live in the PDS | Community JSON implemented; full cross-system customer handoff not qualified |
| Recovery | Tested email recovery and credential revocation; encrypted off-host backup, retention owner and access controls | Existing guide records gaps; no new live drill |
| Restore | Restore the exact backup into an isolated PDS, verify identities, repository records/blobs and login, then record exact image and hashes | Historical drill exists; fresh customer-data drill pending |
| Migration/exit | User-authorized migration to another provider with DID/handle continuity, records/blobs checked and OAuth sessions re-established | Not performed; no migration authority |
| Moderation/operations | Named responsible operator, incident/escalation procedures, monitored quotas, abuse handling, reserved handles and service boundaries | Software controls implemented; staffed service not established |

Do not accept a checksum alone as restore or migration proof. Do not collect private keys or credentials into the public handoff ledger. Customer-facing exports must exclude other members' private reports/session data. Existing local-account merge behavior does not prove AT identity migration.

Before any future managed-hosting release, refresh the upstream PDS version/security review, inspect the actual running digest/configuration without exposing secrets, then perform the separately authorized recovery/export/restore/migration checks. No new account, invite, DNS change, deployment or migration is required to review or use the code delivered in this task.
