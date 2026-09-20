# Database migrations

**Status:** shipped operational guidance (2026-07-14).

Use additive Alembic migrations first. Verify the full history on an empty PostgreSQL database with `make verify`. Before production migration, back up PostgreSQL and complete a restore rehearsal.

Deploy additive schema, then compatible API/frontend/worker images, backfills, and finally deferred destructive cleanup in a later release. Historical billing columns remain dormant compatibility fields; they do not imply a billing contract.

## 20260813_multi_provider_ids: multiple identities per provider

This migration removes the per-user/per-provider uniqueness constraint while retaining global uniqueness for each provider subject. Its downgrade is valid only before any user links a second identity from the same provider. The downgrade checks for such rows and fails closed before restoring the rc.8 constraint. Confirm the duplicate-provider query returns no rows before attempting an rc.8 rollback.

## 20260714_0300: native search outbox update scope

`20260714_0300` is the current head. It retains native segment INSERT and DELETE
outbox events, but emits UPDATE events only when `video_id`, `start_ms`, `end_ms`,
or `text` is named in the update. Diarization's `speaker_label` updates therefore
need no search-index outbox privileges.

The downgrade restores the broad UPDATE trigger. Stop all diarization canaries
before downgrading to `20260714_0200`; the scoped diarization role intentionally
lacks outbox INSERT/sequence privileges and cannot write speaker labels safely
against the downgraded trigger.

## 20260714_0200: hash-only session contract (maintenance-only)

`20260714_0200` drops the plaintext session-token column. It is **not safe for a
rolling or blue/green deployment**. The ordinary release overlay forces
`ALLOW_SESSION_TOKEN_CONTRACT_MIGRATION="false"`; it must remain false for every
ordinary deployment. The ordinary Helm pre-upgrade hook likewise blocks before
this cutover while the opt-in is false; after the database is at 0200, it safely
skips this migration with the opt-in false.

For an existing deployment, use the isolated, preflighted maintenance command
only after a writer drain, verified backup/restore point, and explicit operator
approval. Have an operator review workload and database-session lists before
each destructive step; do not terminate database backends indiscriminately. No
normal release command may override the forced-false setting.

1. Stop user traffic and take and verify a backup.
2. Use exactly one selected Compose project or Helm release throughout this
   window; do not mix its network, database, credentials, or overlays.
3. Review every workload, Job, and database session before each destructive
   step. Do not proceed with active, idle-in-transaction, or unreviewed old
   application sessions. If an approved application session must be
   terminated, identify its PID and owner first; never issue a blanket
   `pg_terminate_backend`.
4. Run one isolated, opted-in migration Job—not a normal `helm upgrade`—and
   verify the exact Alembic head and hash-only schema before deployment.
5. Pause for human verification, deploy only the new hash-only image, then
   restore the recorded workload and scheduling state before reopening traffic.

Once the database is already at 0200, later `upgrade head` invocations safely
skip this migration with the flag false. A downgrade invalidates every session:
plaintext cookie tokens cannot be reconstructed from hashes, so do not resume an
older consumer with live hash-only sessions.

### Guarded Docker Compose equivalent

Deployments using the guarded production stack have one authoritative path:
`scripts/compose_prod.sh`. Do not
construct a partial Compose array or run `docker compose` directly. Before the
window, place the downloaded `release-images.json` at the repository root and
configure `.env.prod` with the matching 0200-aware digest references. The helper
applies the release overlay last, validates the manifest and source commit, and
exposes only named maintenance actions. It never permits a dirty-tree bypass for
deployment or maintenance.

Close external traffic and verify the approved backup/recovery point before the
drain. The first command must pass before recording or changing service state:

```bash
set -euo pipefail

scripts/compose_prod.sh preflight

# Record the running set and approved immutable images before the drain.
mapfile -t RUNNING_SERVICES < <(scripts/compose_prod.sh ps --services --status running)
printf '%s\n' "${RUNNING_SERVICES[@]}"
scripts/compose_prod.sh images

read -r -p "Ingress is closed, backup is verified, and the recorded services/images are correct; type DRAIN: " APPROVAL
test "$APPROVAL" = DRAIN
scripts/compose_prod.sh maintenance session-token-contract-drain --approved

# Review sessions; the named action never terminates database backends.
scripts/compose_prod.sh maintenance session-token-contract-inspect --approved
read -r -p "No old writer or unreviewed database session remains; type MIGRATE: " APPROVAL
test "$APPROVAL" = MIGRATE

# This is the sole action that overrides the ordinary forced-false default.
scripts/compose_prod.sh maintenance session-token-contract-migration --approved
scripts/compose_prod.sh maintenance session-token-contract-verify --approved

read -r -p "The fail-closed head/schema verification passed; type DEPLOY_NEW_IMAGE: " APPROVAL
test "$APPROVAL" = DEPLOY_NEW_IMAGE
scripts/compose_prod.sh deploy

# Confirm every service that was running before the drain is running again.
mapfile -t RESTORED_SERVICES < <(scripts/compose_prod.sh ps --services --status running)
for service in "${RUNNING_SERVICES[@]}"; do
  printf '%s\n' "${RESTORED_SERVICES[@]}" | grep -Fqx -- "$service" || {
    printf 'Previously running service was not restored: %s\n' "$service" >&2
    exit 1
  }
done
```

The final `deploy` re-runs strict preflight and starts only manifest-pinned
images. Do not use an ordinary rolling upgrade or restore an old application
digest after this migration.

### Helm/Kubernetes equivalent

Set the release-specific values below, confirm the image is the new hash-only
application image, and adjust the secret name only after reviewing the release.
The commands record restorable state, tolerate absent optional release
resources, and deliberately fail closed on migration and schema verification:

```bash
set -euo pipefail
export NS=transcript-create RELEASE=transcript-create
export TARGET_TAG=TARGET_TAG
export TARGET_REPOSITORY=registry.example/hasanara
export MIGRATION_IMAGE="${TARGET_REPOSITORY}:${TARGET_TAG}"
export DB_SECRET="${RELEASE}-secrets"
export STATE_DIR="${PWD}/0200-${RELEASE}-state"
mkdir -p "$STATE_DIR"

# Record the release state needed to restore this exact maintenance window.
helm get values "$RELEASE" -n "$NS" --all > "$STATE_DIR/helm-values.yaml"
API_REPLICAS="$(kubectl get deployment "${RELEASE}-api" -n "$NS" -o jsonpath='{.spec.replicas}')"
WORKER_REPLICAS="$(kubectl get deployment "${RELEASE}-worker" -n "$NS" -o jsonpath='{.spec.replicas}')"
printf '%s\n' "$API_REPLICAS" > "$STATE_DIR/api-replicas"
printf '%s\n' "$WORKER_REPLICAS" > "$STATE_DIR/worker-replicas"
kubectl get cronjob -n "$NS" -l "app.kubernetes.io/instance=${RELEASE}" -o jsonpath='{range .items[*]}{.metadata.name}{"\t"}{.spec.suspend}{"\n"}{end}' > "$STATE_DIR/cronjobs.tsv"

# Stop traffic first, then prevent controllers from recreating writers.
while IFS=$'\t' read -r CRONJOB _; do
  [ -z "$CRONJOB" ] || kubectl patch cronjob "$CRONJOB" -n "$NS" --type=merge -p '{"spec":{"suspend":true}}'
done < "$STATE_DIR/cronjobs.tsv"
# Delete only the chart-owned API/worker HPA and PDB; Helm recreates these names.
CHART_HPAS=("${RELEASE}-api" "${RELEASE}-worker")
CHART_PDBS=("${RELEASE}-api" "${RELEASE}-worker")
for RESOURCE in "${CHART_HPAS[@]}"; do kubectl delete hpa "$RESOURCE" -n "$NS" --ignore-not-found; done
for RESOURCE in "${CHART_PDBS[@]}"; do kubectl delete pdb "$RESOURCE" -n "$NS" --ignore-not-found; done
kubectl scale deployment "${RELEASE}-api" "${RELEASE}-worker" -n "$NS" --replicas=0
kubectl wait --for=delete pod -n "$NS" -l "app.kubernetes.io/instance=${RELEASE},app.kubernetes.io/component=api" --timeout=5m || test -z "$(kubectl get pods -n "$NS" -l "app.kubernetes.io/instance=${RELEASE},app.kubernetes.io/component=api" -o name)"
kubectl wait --for=delete pod -n "$NS" -l "app.kubernetes.io/instance=${RELEASE},app.kubernetes.io/component=worker" --timeout=5m || test -z "$(kubectl get pods -n "$NS" -l "app.kubernetes.io/instance=${RELEASE},app.kubernetes.io/component=worker" -o name)"

# Inspect every Job in the namespace: labels can be absent or inherited
# differently by a CronJob. Classify every active Job before proceeding.
kubectl get jobs -n "$NS" -o wide
mapfile -t ACTIVE_JOBS < <(kubectl get jobs -n "$NS" -o jsonpath='{range .items[?(@.status.active)]}{.metadata.name}{"\n"}{end}')
for JOB in "${ACTIVE_JOBS[@]}"; do
  kubectl get "job/$JOB" -n "$NS" -o jsonpath='{.metadata.name}{" owner="}{range .metadata.ownerReferences[*]}{.kind}{":"}{.name}{" "}{end}{"\n"}'
  read -r -p "Classify active Job $JOB; type WAIT, STOP, or BLOCK: " ACTION
  case "$ACTION" in
    WAIT) kubectl wait --for=condition=complete "job/$JOB" -n "$NS" --timeout=10m ;;
    STOP)
      read -r -p "Type STOP_APPROVED to delete $JOB: " APPROVAL
      test "$APPROVAL" = STOP_APPROVED
      kubectl delete "job/$JOB" -n "$NS" --ignore-not-found
      kubectl wait --for=delete "job/$JOB" -n "$NS" --timeout=5m
      ;;
    *) exit 1 ;;
  esac
done

# Select exactly one trusted PostgreSQL command. Use it for both inspections;
# do not assume PostgreSQL is in-cluster. Uncomment and set only one option.
PSQL=()
# PG_POD="$(kubectl get pod -n "$NS" -l app.kubernetes.io/name=postgresql -o jsonpath='{.items[0].metadata.name}')"; PSQL=(kubectl exec -n "$NS" "$PG_POD" -- psql -v ON_ERROR_STOP=1 -U postgres -d transcripts)
# PSQL=(psql -v ON_ERROR_STOP=1 "service=transcripts-admin")
# PSQL=(psql -v ON_ERROR_STOP=1 "$TRUSTED_DATABASE_DSN")
((${#PSQL[@]})) || { printf '%s\n' 'Select an in-cluster or trusted external PSQL command.' >&2; exit 1; }
"${PSQL[@]}" -c "SELECT pid, usename, application_name, state, wait_event_type, query_start, xact_start, left(query, 120) AS query FROM pg_stat_activity WHERE datname = current_database() AND pid <> pg_backend_pid() ORDER BY xact_start NULLS LAST, query_start NULLS LAST;"
read -r -p "Session review complete; type MIGRATE to continue: " APPROVAL
test "$APPROVAL" = MIGRATE

# Isolated one-time Job; do not use helm upgrade with the opt-in value.
kubectl delete job "${RELEASE}-session-contract-migration" -n "$NS" --ignore-not-found
kubectl apply -n "$NS" -f - <<EOF
apiVersion: batch/v1
kind: Job
metadata:
  name: ${RELEASE}-session-contract-migration
spec:
  backoffLimit: 0
  template:
    spec:
      restartPolicy: Never
      containers:
      - name: migrations
        image: ${MIGRATION_IMAGE}
        command: ["python3", "scripts/run_migrations.py", "upgrade"]
        env:
        - name: DATABASE_URL
          valueFrom:
            secretKeyRef:
              name: ${DB_SECRET}
              key: database-url
        - name: ALLOW_SESSION_TOKEN_CONTRACT_MIGRATION
          value: "true"
EOF
kubectl wait --for=condition=complete job/"${RELEASE}-session-contract-migration" -n "$NS" --timeout=10m
kubectl logs job/"${RELEASE}-session-contract-migration" -n "$NS"
"${PSQL[@]}" -c "SELECT version_num = '20260714_0300' AS at_expected_head FROM alembic_version; SELECT NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema = 'public' AND table_name = 'sessions' AND column_name = 'token') AS hash_only_sessions; SELECT 1 / CASE WHEN (SELECT version_num = '20260714_0300' FROM alembic_version) AND NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema = 'public' AND table_name = 'sessions' AND column_name = 'token') THEN 1 ELSE 0 END AS verification_must_be_1;"

# Mandatory human pause: do not deploy until the displayed verification is accepted.
read -r -p "Human schema verification passed; type DEPLOY_NEW_IMAGE to continue: " APPROVAL
test "$APPROVAL" = DEPLOY_NEW_IMAGE

# Restore chart-owned resources with the same 0200-aware application/migration image
# and safe-false hook flag. The normal hook now safely skips 0200.
helm upgrade "$RELEASE" ./charts/transcript-create -n "$NS" --reuse-values --set image.repository="$TARGET_REPOSITORY" --set image.tag="$TARGET_TAG" --set image.digest= --set migrations.image.repository="$TARGET_REPOSITORY" --set migrations.image.tag="$TARGET_TAG" --set migrations.image.digest= --set migrations.allowSessionTokenContractMigration=false --wait --timeout=10m
kubectl scale deployment "${RELEASE}-api" -n "$NS" --replicas="$(cat "$STATE_DIR/api-replicas")"
kubectl scale deployment "${RELEASE}-worker" -n "$NS" --replicas="$(cat "$STATE_DIR/worker-replicas")"
while IFS=$'\t' read -r CRONJOB SUSPEND; do
  [ -z "$CRONJOB" ] || kubectl patch cronjob "$CRONJOB" -n "$NS" --type=merge -p "{\"spec\":{\"suspend\":${SUSPEND:-false}}}"
done < "$STATE_DIR/cronjobs.tsv"
for RESOURCE in "${CHART_HPAS[@]}"; do kubectl get hpa "$RESOURCE" -n "$NS"; done
for RESOURCE in "${CHART_PDBS[@]}"; do kubectl get pdb "$RESOURCE" -n "$NS"; done
test "$(kubectl get deployment "${RELEASE}-api" -n "$NS" -o jsonpath='{.spec.replicas}')" = "$(cat "$STATE_DIR/api-replicas")"
test "$(kubectl get deployment "${RELEASE}-worker" -n "$NS" -o jsonpath='{.spec.replicas}')" = "$(cat "$STATE_DIR/worker-replicas")"
while IFS=$'\t' read -r CRONJOB SUSPEND; do
  [ -z "$CRONJOB" ] || test "$(kubectl get cronjob "$CRONJOB" -n "$NS" -o jsonpath='{.spec.suspend}')" = "${SUSPEND:-false}"
done < "$STATE_DIR/cronjobs.tsv"
kubectl rollout status deployment/"${RELEASE}-api" -n "$NS" --timeout=10m
kubectl rollout status deployment/"${RELEASE}-worker" -n "$NS" --timeout=10m
```

Analytics credential scrub and session rotation are irreversible boundaries: after rollout, do not restore an image that writes session credentials to events. Search outbox backfills must reconcile PostgreSQL/OpenSearch counts before OpenSearch becomes primary.
