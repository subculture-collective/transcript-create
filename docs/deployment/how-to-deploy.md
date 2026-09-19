# Immutable production deployment quick reference

Use this reference only after the ordered gates in [private-beta.md](private-beta.md)
have been satisfied for the intended release. It does not replace that runbook,
authorize deployment, or establish that a candidate is ready.

## Select the release

Run on the deployment host, from its verified HasanAra checkout (historically
`/home/onnwee/Projects/subcult/hasanara` on Almaz). Inspect the checkout before
changing branches; preserve uncommitted work. `gitea` is the authoritative remote.

```bash
rtk git status --short
rtk git remote -v
rtk git fetch gitea
rtk git branch --show-current
rtk git rev-parse HEAD
```

Switch to the approved release branch and exact commit associated with its signed
evidence bundle. Do not use an old branch name copied from a previous release or
a detached HEAD. Confirm the commit again after switching.

## Obtain the manifest and recovery evidence

Download the matching `release-images.json` from the verified signed release
evidence bundle into the repository root. It is intentionally gitignored. The
manifest's source commit must equal HEAD, and its immutable image digests/service
mapping must match the production Compose configuration. Do not construct a
replacement manifest from whatever images happen to be running or from mutable
tags. The release workflow owns manifest generation and qualification.

Before deployment, retain the existing manifest, exact image identities, migration
head, and verified backup/recovery evidence in the restricted release packet.
Complete the staging/recovery gates in the full runbook. Do not print environment
files or resolved secret-bearing Compose configuration into public logs.

## Preflight and deploy

The helper selects `.env.prod`, the fixed production overlays and project, and
clears inherited shell configuration. Invoke the helper rather than reconstructing
its Compose invocation by hand.

```bash
rtk proxy bash scripts/compose_prod.sh preflight
```

Resolve each failure before proceeding. A source mismatch needs the matching
release source and manifest; an image mismatch needs the correct immutable image
configuration. Preserve dirty work instead of deleting it to satisfy preflight.
Disabled-profile retirement has its own approved maintenance path in the full
runbook; do not remove arbitrary containers.

After the release gates and deployment authorization are satisfied:

```bash
rtk proxy bash scripts/compose_prod.sh deploy
```

This reruns preflight and executes `docker compose up -d --no-build --pull always`
with the helper's fixed configuration. Successful command completion alone is not
successful release qualification.

## Read back and verify

```bash
rtk proxy bash scripts/compose_prod.sh ps --all
rtk proxy bash scripts/compose_prod.sh images
rtk proxy bash scripts/compose_prod.sh logs --tail 80 migrations api frontend
```

Confirm migrations exited with code zero; investigate any missing migration
service, failed container or unexpected restart. Compare running image identities
with the approved manifest. The Compose service is named `frontend`; do not infer
service names from container display names.

Use the configured ingress health URL and verify the actual browser journeys:
sign-in, search, playback and any enabled community/sharing features. Check CSP,
cache behavior, background processing, backup recency and alert delivery as
required by the full runbook. A healthy API does not prove a working browser UI,
completed ingestion or a matching image revision. Retain exact release evidence
without secrets.

## Recovery

For an additive migration, use the previously recorded compatible immutable image
set and its matching source/manifest under the release procedure. Do not invent
new digest combinations during rollback. Some session and analytics migrations
are roll-forward-only boundaries: follow [MIGRATIONS.md](../MIGRATIONS.md) before
selecting an older image. Never treat an ignored migration-log error as success.

References: [private-beta.md](private-beta.md),
[production-readiness.md](../operations/production-readiness.md),
`scripts/compose_prod.sh`, and `scripts/release_preflight.py`.
