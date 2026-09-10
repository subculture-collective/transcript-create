#!/usr/bin/env bash
# Run the exact HasanAra production stack without inherited shell variables.
set -Eeuo pipefail

repo_root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
cd "$repo_root"

readonly -a CLEAN_ENV=(env -i PATH="$PATH" HOME="$HOME" USER="${USER:-}" HASANARA_ENV_FILE=.env.prod)
readonly -a COMPOSE=(docker compose
    --project-name hasanara
    --env-file .env.prod
    --file docker-compose.yml
    --file docker-compose.gtx1080.yml
    --file docker-compose.hasanara.yml
    --file docker-compose.storage.yml
    --file docker-compose.pitr.yml
    --file docker-compose.release.yml)

run_preflight() { "${CLEAN_ENV[@]}" python3 scripts/release_preflight.py; }
run_retirement_preflight() { "${CLEAN_ENV[@]}" python3 scripts/release_preflight.py --allow-disabled-profile-services; }
compose() { "${CLEAN_ENV[@]}" "${COMPOSE[@]}" "$@"; }
run_compose() { exec "${CLEAN_ENV[@]}" "${COMPOSE[@]}" "$@"; }
usage() { printf '%s\n' 'usage: scripts/compose_prod.sh {preflight|deploy|maintenance|config|ps|logs|top|images|version} [arguments]' >&2; }
is_uuid() { [[ $1 =~ ^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$ ]]; }

check_diarization_role() {
    compose exec -T db psql -v ON_ERROR_STOP=1 -U postgres -d transcripts < scripts/check_diarization_role.sql
}

# Canary state is global so EXIT/INT/TERM handlers never interpolate locals.
canary_video_id= canary_token= canary_container_name= canary_container_id= canary_acquisition_possible=false canary_acquired=false canary_done=false
psql_diarization() { compose exec -T db psql -X -v ON_ERROR_STOP=1 -U hasanara_diarization -d transcripts "$@"; }
psql_diarization_sql() { local sql=$1; shift; psql_diarization "$@" -f - <<<"$sql"; }
canary_lease() { printf 'canary-lease:%s' "$1"; }
canary_finalizing() { printf 'canary-finalizing:%s' "$1"; }
canary_failed() { printf 'canary-failed:%s' "$1"; }

acquire_canary() {
    # Set this before opening psql: a signal can arrive after COMMIT but before
    # Bash receives control to set canary_acquired.
    canary_acquisition_possible=true
    psql_diarization_sql "BEGIN;
      SELECT pg_advisory_xact_lock(hashtext('hasanara-diarization-canary'));
      SELECT 1 / CASE WHEN NOT EXISTS (SELECT 1 FROM videos WHERE diarization_error LIKE 'canary-%') THEN 1 ELSE 0 END;
      UPDATE videos SET diarization_state='running', diarization_error='canary-lease:' || :'token', updated_at=now()
       WHERE id=:'video_id'::uuid AND state='completed' AND diarization_state='pending'
         AND wav_path IS NOT NULL AND duration_seconds IS NOT NULL AND duration_seconds <= 600
         AND EXISTS (SELECT 1 FROM segments WHERE video_id=:'video_id'::uuid)
         AND NOT EXISTS (SELECT 1 FROM videos WHERE diarization_error LIKE 'canary-%');
      SELECT 1 / CASE WHEN EXISTS (SELECT 1 FROM videos WHERE id=:'video_id'::uuid AND diarization_state='running' AND diarization_error='canary-lease:' || :'token') THEN 1 ELSE 0 END;
      COMMIT;" -v video_id="$canary_video_id" -v token="$canary_token" >/dev/null
    canary_acquired=true
}

# Prints exactly fenced, absent, or uncertain.  Only absence of every canary
# marker on the target is safe before acquisition; any other token fails closed.
fence_canary_failure() {
    local result
    result=$(psql_diarization_sql "WITH fenced AS (
      UPDATE videos SET diarization_state='failed', diarization_error='canary-failed:' || :'token', updated_at=now()
       WHERE id=:'video_id'::uuid
         AND ((diarization_state='running' AND diarization_error='canary-lease:' || :'token')
           OR (diarization_state='completed' AND diarization_error='canary-finalizing:' || :'token'))
       RETURNING 1
    ) SELECT CASE WHEN EXISTS (SELECT 1 FROM fenced) OR EXISTS (SELECT 1 FROM videos WHERE id=:'video_id'::uuid AND diarization_state='failed' AND diarization_error='canary-failed:' || :'token') THEN 'fenced' WHEN EXISTS (SELECT 1 FROM videos WHERE id=:'video_id'::uuid AND (diarization_error IS NULL OR diarization_error NOT LIKE 'canary-%')) THEN 'absent' ELSE 'uncertain' END;" -At -v video_id="$canary_video_id" -v token="$canary_token") || return 1
    [[ $result == fenced || $result == absent ]] || return 1
    printf '%s\n' "$result"
}

finalize_canary_success() {
    local result
    result=$(psql_diarization_sql "WITH finalized AS (
      UPDATE videos SET diarization_error=NULL, updated_at=now()
       WHERE id=:'video_id'::uuid AND diarization_state='completed' AND diarization_error='canary-finalizing:' || :'token'
         AND (SELECT count(DISTINCT speaker_label) FROM segments WHERE video_id=:'video_id'::uuid AND speaker_label IS NOT NULL) BETWEEN 1 AND 20
       RETURNING 1
    ) SELECT count(*) FROM finalized;" -At -v video_id="$canary_video_id" -v token="$canary_token") || return 1
    [[ $result == 1 ]]
}

container_details_match() {
    local details id name token
    details=$(timeout --kill-after=5s 10s "${CLEAN_ENV[@]}" docker container inspect --format '{{.Id}}|{{.Name}}|{{index .Config.Labels "hasanara.canary-token"}}' "$canary_container_id") || return 1
    IFS='|' read -r id name token <<<"$details"
    [[ $id == "$canary_container_id" && $name == "/$canary_container_name" && $token == "$canary_token" ]]
}

cleanup_canary_container() {
    local ids count line
    [[ -n $canary_container_name && -n $canary_token ]] || return 1
    if [[ -z $canary_container_id ]]; then
        ids=$(timeout --kill-after=5s 10s "${CLEAN_ENV[@]}" docker container ls --all --no-trunc --filter "label=hasanara.canary-token=$canary_token" --filter "name=^/${canary_container_name}$" --format '{{.ID}}') || return 1
        count=0
        while IFS= read -r line; do
            [[ -n $line ]] && ((count += 1))
        done <<<"$ids"
        [[ $count == 0 ]] && return 0
        [[ $count == 1 ]] || return 1
        canary_container_id=$ids
        [[ $canary_container_id =~ ^[0-9a-f]{64}$ ]] || return 1
    fi
    container_details_match || return 1
    timeout --kill-after=5s 30s "${CLEAN_ENV[@]}" docker container stop --time 20 "$canary_container_id" >/dev/null || return 1
    timeout --kill-after=5s 10s "${CLEAN_ENV[@]}" docker container rm --force "$canary_container_id" >/dev/null || return 1
    ids=$(timeout --kill-after=5s 10s "${CLEAN_ENV[@]}" docker container ls --all --no-trunc --filter "name=^/${canary_container_name}$" --format '{{.ID}}') || return 1
    [[ -z $ids ]]
}

on_canary_exit() {
    local status=$?
    trap - EXIT INT TERM
    if [[ $canary_acquisition_possible == true && $canary_done != true ]]; then
        # Do not clear or report success when the abort fence cannot be proven.
        if ! fence_canary_failure; then exit 1; fi
        cleanup_canary_container || exit 1
    fi
    exit "$status"
}
on_canary_signal() {
    trap - EXIT INT TERM
    if [[ $canary_acquisition_possible != true ]] || ! fence_canary_failure >/dev/null; then exit 1; fi
    cleanup_canary_container || exit 1
    exit "$1"
}

run_diarization_canary() {
    canary_video_id=$1
    canary_token=$(</proc/sys/kernel/random/uuid) || return 1
    is_uuid "$canary_token" || return 1
    canary_container_name="hasanara-diarization-canary-${canary_video_id}-${canary_token}"
    canary_container_id=; canary_acquisition_possible=false; canary_acquired=false; canary_done=false
    run_preflight
    check_diarization_role
    trap on_canary_exit EXIT
    trap 'on_canary_signal 130' INT
    trap 'on_canary_signal 143' TERM
    acquire_canary
    compose --profile diarization run -d --no-deps --name "$canary_container_name" --label "hasanara.canary-token=$canary_token" \
      -e "DIARIZATION_ALLOWED_VIDEO_IDS=$canary_video_id" -e DIARIZATION_REQUIRE_ALLOWLIST=true \
      -e DIARIZATION_CANARY_MODE=true -e "DIARIZATION_CANARY_TOKEN=$canary_token" \
      -e DIARIZATION_MAX_JOBS_PER_PROCESS=1 -e DIARIZATION_EXIT_WHEN_IDLE=true -e DIARIZATION_MAX_DURATION_SECONDS=600 \
      -e DIARIZATION_DEVICE=cpu -e HF_HUB_OFFLINE=1 -e TRANSFORMERS_OFFLINE=1 -e DIARIZATION_STRICT=true diarization-worker >/dev/null
    canary_container_id=$(timeout --kill-after=5s 10s "${CLEAN_ENV[@]}" docker container inspect --format '{{.Id}}' "$canary_container_name") || return 1
    [[ $canary_container_id =~ ^[0-9a-f]{64}$ ]] || return 1
    local worker_status
    worker_status=$(timeout --signal=TERM --kill-after=30s 20m "${CLEAN_ENV[@]}" docker container wait "$canary_container_id") || { fence_canary_failure && cleanup_canary_container; return 1; }
    [[ $worker_status == 0 ]] || { fence_canary_failure && cleanup_canary_container; return 1; }
    cleanup_canary_container || return 1
    assert_exact_token_container_absent || return 1
    finalize_canary_success || return 1
    canary_done=true
    trap - EXIT INT TERM
}

assert_exact_token_container_absent() {
    local token_ids name_ids
    token_ids=$(timeout --kill-after=5s 10s "${CLEAN_ENV[@]}" docker container ls --all --no-trunc --filter "label=hasanara.canary-token=$canary_token" --format '{{.ID}}') || return 1
    name_ids=$(timeout --kill-after=5s 10s "${CLEAN_ENV[@]}" docker container ls --all --no-trunc --filter "name=^/${canary_container_name}$" --format '{{.ID}}') || return 1
    [[ -z $token_ids && -z $name_ids ]]
}

recover_diarization_canary() {
    canary_video_id=$1; canary_token=$2; canary_container_name="hasanara-diarization-canary-${canary_video_id}-${canary_token}"
    assert_exact_token_container_absent || return 1
    psql_diarization_sql "BEGIN;
      SELECT pg_advisory_xact_lock(hashtext('hasanara-diarization-canary'));
      WITH target AS (SELECT id, diarization_state, diarization_error FROM videos WHERE id=:'video_id'::uuid FOR UPDATE), recovered AS (UPDATE videos v SET diarization_error=NULL, updated_at=now() FROM target t WHERE v.id=t.id AND t.diarization_state='completed' AND t.diarization_error='canary-finalizing:' || :'token' AND (SELECT count(DISTINCT speaker_label) FROM segments WHERE video_id=t.id AND speaker_label IS NOT NULL) BETWEEN 1 AND 20 RETURNING 1), cleared AS (UPDATE segments s SET speaker_label=NULL FROM target t WHERE s.video_id=t.id AND t.diarization_state IN ('running','failed') AND t.diarization_error IN ('canary-lease:' || :'token', 'canary-failed:' || :'token') RETURNING s.id), reset AS (UPDATE videos v SET diarization_state='pending', diarization_error=NULL, updated_at=now() FROM target t WHERE v.id=t.id AND t.diarization_state IN ('running','failed') AND t.diarization_error IN ('canary-lease:' || :'token', 'canary-failed:' || :'token') RETURNING 1) SELECT 1 / CASE WHEN EXISTS (SELECT 1 FROM recovered) OR EXISTS (SELECT 1 FROM reset) THEN 1 ELSE 0 END;
      COMMIT;" -v video_id="$canary_video_id" -v token="$canary_token" >/dev/null
}

# The enrichment canary is deliberately separate from the sustained queue and
# from the diarization canary state above. A fixed container name makes
# concurrent invocations fail atomically at Docker create time.
readonly enrichment_canary_model=deepseek/deepseek-v4-pro
readonly enrichment_canary_prompt=archive-episode-enrichment-v7
readonly enrichment_canary_container_name=hasanara-archive-enrichment-canary
enrichment_canary_video_id=''; enrichment_canary_token=''; enrichment_canary_container_id=''; enrichment_canary_started_at=''
enrichment_canary_evidence_dir=''; enrichment_canary_started=false; enrichment_canary_done=false
enrichment_canary_evidence_root=deploy-backups/archive-enrichment-canaries
enrichment_canary_preexisting_fingerprint=''
enrichment_canary_protected_fingerprint=''

psql_admin() { compose exec -T db psql -X -v ON_ERROR_STOP=1 -U postgres -d transcripts "$@"; }
psql_admin_sql() { local sql=$1; shift; psql_admin "$@" -f - <<<"$sql"; }

assert_container_healthy() {
    local container=$1 details
    details=$(timeout --kill-after=5s 10s "${CLEAN_ENV[@]}" docker container inspect \
      --format '{{.State.Status}}|{{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}}' "$container") || return 1
    [[ $details == running\|healthy ]]
}

assert_enrichment_queue_inert() {
    local details
    grep -Eq '^ARCHIVE_ENRICHMENT_ENABLED=(false|False|FALSE|0)$' .env.prod || return 1
    grep -Eq '^ARCHIVE_ENRICHMENT_PUBLISH=(false|False|FALSE|0)$' .env.prod || return 1
    details=$(timeout --kill-after=5s 10s "${CLEAN_ENV[@]}" docker container inspect \
      --format '{{.State.Status}}|{{.HostConfig.RestartPolicy.Name}}' hasanara-archive-enrichment-queue-1) || return 1
    [[ $details == exited\|no ]]
    [[ $(psql_admin -At -c "SELECT count(*) FROM archive_extraction_runs WHERE status = 'running';") == 0 ]]
}

check_enrichment_canary_target() {
    psql_admin_sql "SELECT 1 / CASE WHEN EXISTS (
        SELECT 1 FROM videos v
        WHERE v.id = :'video_id'::uuid
          AND v.state = 'completed'
          AND v.duration_seconds > 5400 AND v.duration_seconds <= 10800
          AND EXISTS (
            SELECT 1 FROM transcript_blocks tb WHERE tb.video_id = v.id
            UNION ALL SELECT 1 FROM segments s WHERE s.video_id = v.id
            UNION ALL SELECT 1 FROM youtube_transcripts yt
              JOIN youtube_segments ys ON ys.youtube_transcript_id = yt.id WHERE yt.video_id = v.id
          )
          AND NOT EXISTS (SELECT 1 FROM archive_video_chapters c WHERE c.video_id = v.id)
          AND NOT EXISTS (
            SELECT 1 FROM archive_label_assignments a WHERE a.video_id = v.id AND a.source = 'llm'
          )
          AND NOT EXISTS (
            SELECT 1 FROM archive_extraction_runs r
            WHERE r.video_id = v.id AND r.model_name = :'model' AND r.prompt_version = :'prompt'
              AND r.status IN ('running', 'failed') AND r.started_at > now() - interval '24 hours'
          )
      ) THEN 1 ELSE 0 END AS target_is_eligible;" -v video_id="$enrichment_canary_video_id" \
      -v model="$enrichment_canary_model" -v prompt="$enrichment_canary_prompt" >/dev/null
}

check_enrichment_canary_guardrails() {
    psql_admin_sql "WITH attempts AS (
        SELECT status, metrics, started_at FROM archive_extraction_runs
        WHERE model_name = :'model' AND started_at >= now() - interval '24 hours'
      ), recent AS (
        SELECT status FROM attempts WHERE status IN ('completed', 'failed') ORDER BY started_at DESC LIMIT 20
      ), snapshot AS (
        SELECT
          (SELECT count(*) FROM attempts) AS attempts,
          (SELECT COALESCE(sum(CASE WHEN jsonb_typeof(metrics -> 'cost_usd') = 'number'
            THEN (metrics ->> 'cost_usd')::numeric ELSE 0 END), 0) FROM attempts) AS cost,
          (SELECT count(*) FROM recent) AS finished,
          (SELECT count(*) FROM recent WHERE status = 'failed') AS failures
      )
      SELECT 1 / CASE WHEN attempts < 20 AND cost < 5.0
        AND (finished < 20 OR failures::numeric / finished < 0.25)
        THEN 1 ELSE 0 END AS guardrails_allow_one_attempt FROM snapshot;" \
      -v model="$enrichment_canary_model" >/dev/null
}

enrichment_canary_assignment_fingerprint() {
    psql_admin_sql "SELECT md5(COALESCE(
      (SELECT jsonb_agg(to_jsonb(a) ORDER BY a.id)::text FROM archive_label_assignments a
       WHERE a.video_id = :'video_id'::uuid AND a.source <> 'llm'), '[]')) AS preexisting_assignment_fingerprint;" \
      -At -v video_id="$enrichment_canary_video_id"
}

enrichment_canary_protected_label_fingerprint() {
    psql_admin_sql "WITH protected AS (
      SELECT * FROM archive_labels
      WHERE status IN ('published', 'rejected', 'merged', 'hidden') OR source IN ('admin', 'seed', 'hybrid')
    ) SELECT md5(jsonb_build_object(
      'labels', COALESCE((SELECT jsonb_agg(to_jsonb(l) ORDER BY l.id) FROM protected l), '[]'::jsonb),
      'aliases', COALESCE((SELECT jsonb_agg(to_jsonb(a) ORDER BY a.id) FROM archive_label_aliases a
        JOIN protected l ON l.id = a.label_id), '[]'::jsonb))::text);" -At
}

verify_enrichment_canary_protected_labels() {
    local after
    after=$(enrichment_canary_protected_label_fingerprint) || return 1
    [[ $after =~ ^[0-9a-f]{32}$ ]] || return 1
    local outcome=failed
    [[ $after != "$enrichment_canary_protected_fingerprint" ]] || outcome=passed
    printf '{"protected_labels":"%s","before":"%s","after":"%s"}\n' \
      "$outcome" "$enrichment_canary_protected_fingerprint" "$after" \
      | tee "$enrichment_canary_evidence_dir/protected-label-verification.json"
    chmod 600 "$enrichment_canary_evidence_dir/protected-label-verification.json"
    [[ $outcome == passed ]]
}

enrichment_container_details_match() {
    local details id name token
    details=$(timeout --kill-after=5s 10s "${CLEAN_ENV[@]}" docker container inspect \
      --format '{{.Id}}|{{.Name}}|{{index .Config.Labels "hasanara.enrichment-canary-token"}}' \
      "$enrichment_canary_container_id") || return 1
    IFS='|' read -r id name token <<<"$details"
    [[ $id == "$enrichment_canary_container_id" && $name == "/$enrichment_canary_container_name" && $token == "$enrichment_canary_token" ]]
}

cleanup_enrichment_canary_container() {
    local ids count line
    [[ -n $enrichment_canary_token ]] || return 1
    if [[ -z $enrichment_canary_container_id ]]; then
        ids=$(timeout --kill-after=5s 10s "${CLEAN_ENV[@]}" docker container ls --all --no-trunc \
          --filter "label=hasanara.enrichment-canary-token=$enrichment_canary_token" \
          --filter "name=^/${enrichment_canary_container_name}$" --format '{{.ID}}') || return 1
        count=0
        while IFS= read -r line; do [[ -n $line ]] && ((count += 1)); done <<<"$ids"
        [[ $count == 0 ]] && return 0
        [[ $count == 1 ]] || return 1
        enrichment_canary_container_id=$ids
        [[ $enrichment_canary_container_id =~ ^[0-9a-f]{64}$ ]] || return 1
    fi
    enrichment_container_details_match || return 1
    timeout --kill-after=5s 30s "${CLEAN_ENV[@]}" docker container stop --time 20 \
      "$enrichment_canary_container_id" >/dev/null 2>&1 || true
    timeout --kill-after=5s 10s "${CLEAN_ENV[@]}" docker container rm --force \
      "$enrichment_canary_container_id" >/dev/null || return 1
    ids=$(timeout --kill-after=5s 10s "${CLEAN_ENV[@]}" docker container ls --all --no-trunc \
      --filter "name=^/${enrichment_canary_container_name}$" --format '{{.ID}}') || return 1
    [[ -z $ids ]] || return 1
    enrichment_canary_container_id=''
}

fence_enrichment_canary_run() {
    local fenced
    [[ -n $enrichment_canary_started_at ]] || return 0
    fenced=$(psql_admin_sql "WITH fenced AS (
        UPDATE archive_extraction_runs
        SET status = 'cancelled',
            metrics = COALESCE(metrics, '{}'::jsonb) || jsonb_build_object(
              'reason', 'canary_interrupted', 'invocation_id', :'token'
            ),
            error = 'guarded enrichment canary interrupted', finished_at = now()
        WHERE video_id = :'video_id'::uuid AND model_name = :'model' AND prompt_version = :'prompt'
          AND status = 'running' AND started_at >= :'started_at'::timestamptz
        RETURNING 1
      ) SELECT count(*) FROM fenced;" -At -v video_id="$enrichment_canary_video_id" \
      -v token="$enrichment_canary_token" -v started_at="$enrichment_canary_started_at" \
      -v model="$enrichment_canary_model" -v prompt="$enrichment_canary_prompt") || return 1
    [[ $fenced == 0 || $fenced == 1 ]]
}

assert_enrichment_canary_container_absent() {
    local ids
    ids=$(timeout --kill-after=5s 10s "${CLEAN_ENV[@]}" docker container ls --all --no-trunc \
      --filter "name=^/${enrichment_canary_container_name}$" --format '{{.ID}}') || return 1
    [[ -z $ids ]]
}

verify_enrichment_canary_result() {
    local acceptance
    acceptance=$(psql_admin_sql "WITH target_run AS (
        SELECT id, metrics FROM archive_extraction_runs
        WHERE video_id = :'video_id'::uuid AND model_name = :'model' AND prompt_version = :'prompt'
          AND started_at >= :'started_at'::timestamptz
      ), stored AS (
        SELECT t.id,
          (SELECT count(*) FROM archive_video_chapters c
            WHERE c.video_id = :'video_id'::uuid AND c.run_id = t.id) AS chapters,
          (SELECT count(*) FROM archive_label_assignments a
            WHERE a.video_id = :'video_id'::uuid AND a.run_id = t.id) AS assignments,
          (SELECT count(DISTINCT a.label_id) FROM archive_label_assignments a
            WHERE a.video_id = :'video_id'::uuid AND a.run_id = t.id) AS labels,
          (SELECT count(*) FROM archive_label_assignments a
            WHERE a.video_id = :'video_id'::uuid AND a.run_id = t.id
              AND a.evidence -> 0 ->> 'extractor' = 'llm_category'
              AND a.component_scores ->> 'controlled_taxonomy' = '1.0') AS categories
        FROM target_run t
      ), checks AS (
        SELECT
          (SELECT count(*) FROM target_run) = 1 AS one_run,
          (SELECT count(*) FROM archive_extraction_runs r JOIN target_run t ON t.id = r.id
            WHERE r.status = 'completed') = 1 AS completed,
          (SELECT count(*) FROM target_run
            WHERE (metrics ->> 'window_count')::integer = 2
              AND (metrics ->> 'cost_usd')::numeric <= 1.0
              AND (metrics -> 'repairs' ->> 'evidence_overlap_violations')::integer = 0
              AND (metrics ->> 'categories')::integer >= 1) = 1 AS metrics_valid,
          (SELECT count(*) FROM target_run t JOIN stored s ON s.id = t.id
            WHERE s.chapters = (t.metrics ->> 'chapters')::integer
              AND s.assignments = (t.metrics ->> 'assignments')::integer
              AND s.labels = (t.metrics ->> 'labels')::integer
              AND s.categories = (t.metrics ->> 'categories')::integer
              AND s.categories >= 1) = 1 AS stored_counts_match,
          (SELECT count(*) FROM archive_video_chapters c JOIN target_run t ON t.id = c.run_id
            WHERE c.status = 'candidate' AND c.source = 'automatic') >= 4 AS candidate_chapters,
          (SELECT min(c.start_ms) = 0 AND max(c.end_ms) = v.duration_seconds * 1000
              AND count(*) = count(DISTINCT c.start_ms)
              AND count(*) FILTER (WHERE c.start_ms = round(v.duration_seconds * 1000 / 2.0)) >= 1
            FROM archive_video_chapters c JOIN target_run t ON t.id = c.run_id
            JOIN videos v ON v.id = c.video_id GROUP BY v.duration_seconds) AS chapter_coverage,
          NOT EXISTS (SELECT 1 FROM archive_video_chapters c JOIN target_run t ON t.id = c.run_id
            WHERE c.status <> 'candidate' OR c.source <> 'automatic') AS chapters_review_only,
          NOT EXISTS (SELECT 1 FROM archive_label_assignments a JOIN target_run t ON t.id = a.run_id
            WHERE a.status <> 'candidate' OR a.publish_tier <> 'bronze' OR a.source <> 'llm') AS labels_review_only,
          (SELECT COALESCE(sum(CASE WHEN jsonb_typeof(metrics -> 'cost_usd') = 'number'
            THEN (metrics ->> 'cost_usd')::numeric ELSE 0 END), 0)
            FROM archive_extraction_runs WHERE model_name = :'model'
              AND started_at >= now() - interval '24 hours') < 5.0 AS daily_cost_valid
      ) SELECT CASE WHEN one_run AND completed AND metrics_valid AND candidate_chapters
          AND stored_counts_match AND chapter_coverage AND chapters_review_only AND labels_review_only AND daily_cost_valid
        THEN 'passed' ELSE 'failed' END AS canary_acceptance FROM checks;" \
      -v video_id="$enrichment_canary_video_id" -v started_at="$enrichment_canary_started_at" \
      -v model="$enrichment_canary_model" -v prompt="$enrichment_canary_prompt" -At) || return 1
    printf '{"canary_acceptance":"%s"}\n' "$acceptance" \
      | tee "$enrichment_canary_evidence_dir/database-verification.json"
    if [[ $acceptance != passed ]]; then
        printf '%s\n' 'archive enrichment canary acceptance failed; evidence preserved' >&2
        return 1
    fi
}

on_enrichment_canary_exit() {
    local status=$?
    trap - EXIT INT TERM
    if [[ $enrichment_canary_started == true && $enrichment_canary_done != true ]]; then
        cleanup_enrichment_canary_container || exit 1
        fence_enrichment_canary_run || exit 1
        verify_enrichment_canary_protected_labels || exit 1
    fi
    exit "$status"
}

on_enrichment_canary_signal() {
    trap - EXIT INT TERM
    if [[ $enrichment_canary_started != true ]]; then exit 1; fi
    cleanup_enrichment_canary_container || exit 1
    fence_enrichment_canary_run || exit 1
    verify_enrichment_canary_protected_labels || exit 1
    exit "$1"
}

run_enrichment_canary() {
    enrichment_canary_video_id=$1
    enrichment_canary_token=$(</proc/sys/kernel/random/uuid) || return 1
    is_uuid "$enrichment_canary_token" || return 1
    enrichment_canary_container_id=''; enrichment_canary_started_at=''
    enrichment_canary_started=false; enrichment_canary_done=false
    run_preflight
    assert_container_healthy hasanara-api
    assert_container_healthy hasanara-db
    assert_container_healthy hasanara-redis
    assert_container_healthy hasanara-summary-refresher
    assert_container_healthy hasanara-archive-intelligence-refresher
    assert_enrichment_queue_inert
    assert_enrichment_canary_container_absent
    check_enrichment_canary_target
    check_enrichment_canary_guardrails
    enrichment_canary_started_at=$(psql_admin -At -c 'SELECT clock_timestamp();') || return 1
    [[ -n $enrichment_canary_started_at ]] || return 1
    enrichment_canary_evidence_dir="${enrichment_canary_evidence_root}/$(date -u +%Y%m%dT%H%M%SZ)-${enrichment_canary_video_id}-${enrichment_canary_token}"
    mkdir -p -- "$enrichment_canary_evidence_dir"
    chmod 700 "$enrichment_canary_evidence_dir"
    enrichment_canary_preexisting_fingerprint=$(enrichment_canary_assignment_fingerprint) || return 1
    [[ $enrichment_canary_preexisting_fingerprint =~ ^[0-9a-f]{32}$ ]] || return 1
    enrichment_canary_protected_fingerprint=$(enrichment_canary_protected_label_fingerprint) || return 1
    [[ $enrichment_canary_protected_fingerprint =~ ^[0-9a-f]{32}$ ]] || return 1
    printf '{"preexisting_assignment_fingerprint":"%s","protected_label_fingerprint":"%s"}\n' \
      "$enrichment_canary_preexisting_fingerprint" "$enrichment_canary_protected_fingerprint" \
      >"$enrichment_canary_evidence_dir/preflight.json"
    chmod 600 "$enrichment_canary_evidence_dir/preflight.json"
    trap on_enrichment_canary_exit EXIT
    trap 'on_enrichment_canary_signal 130' INT
    trap 'on_enrichment_canary_signal 143' TERM
    enrichment_canary_started=true
    compose run -d --no-deps --name "$enrichment_canary_container_name" \
      --label "hasanara.enrichment-canary-token=$enrichment_canary_token" \
      -e ARCHIVE_ENRICHMENT_ENABLED=true -e ARCHIVE_ENRICHMENT_PUBLISH=false -e ARCHIVE_ENRICHMENT_AUTO_APPROVE=false \
      -e "ARCHIVE_ENRICHMENT_MODEL=$enrichment_canary_model" -e ARCHIVE_ENRICHMENT_MAX_WINDOW_MINUTES=90 \
      -e ARCHIVE_ENRICHMENT_MAX_COST_USD_PER_VIDEO=1.00 archive-enrichment-queue \
      python3 /app/scripts/run_archive_enrichment_queue.py --once --video-id "$enrichment_canary_video_id" >/dev/null
    enrichment_canary_container_id=$(timeout --kill-after=5s 10s "${CLEAN_ENV[@]}" docker container inspect \
      --format '{{.Id}}' "$enrichment_canary_container_name") || return 1
    [[ $enrichment_canary_container_id =~ ^[0-9a-f]{64}$ ]] || return 1
    enrichment_container_details_match || return 1
    local worker_status
    worker_status=$(timeout --signal=TERM --kill-after=30s 20m "${CLEAN_ENV[@]}" docker container wait \
      "$enrichment_canary_container_id") || return 1
    timeout --kill-after=5s 10s "${CLEAN_ENV[@]}" docker container logs "$enrichment_canary_container_id" \
      | tee "$enrichment_canary_evidence_dir/result.json"
    chmod 600 "$enrichment_canary_evidence_dir/result.json"
    [[ $worker_status == 0 ]] || return 1
    grep -q '"status": "completed"' "$enrichment_canary_evidence_dir/result.json" || return 1
    cleanup_enrichment_canary_container
    assert_enrichment_canary_container_absent
    enrichment_canary_started=false
    verify_enrichment_canary_protected_labels
    verify_enrichment_canary_result
    [[ $(enrichment_canary_assignment_fingerprint) == "$enrichment_canary_preexisting_fingerprint" ]]
    assert_enrichment_queue_inert
    assert_container_healthy hasanara-api
    assert_container_healthy hasanara-db
    enrichment_canary_done=true
    trap - EXIT INT TERM
    printf 'evidence_dir=%s\n' "$enrichment_canary_evidence_dir"
}

[[ ${BASH_SOURCE[0]} == "$0" ]] || return 0

command=${1:-}
case "$command" in
    preflight)
        shift
        exec "${CLEAN_ENV[@]}" python3 scripts/release_preflight.py "$@"
        ;;
    deploy)
        shift
        if (($# != 0)); then usage; exit 64; fi
        run_preflight
        run_compose up -d --no-build --pull always
        ;;
    maintenance)
        shift
        if [[ ${1:-} == archive-enrichment-canary ]]; then
            if (($# != 3)) || ! is_uuid "${2:-}" || [[ ${3:-} != --approved ]]; then
                printf '%s\n' 'archive-enrichment-canary requires exactly one UUID and --approved' >&2
                exit 64
            fi
            run_enrichment_canary "$2"; exit $?
        fi
        if [[ ${1:-} == recover-attention-backlog ]]; then
            if (($# != 3 && $# != 5)) || [[ ${2:-} != alignment && ${2:-} != yt-dlp ]] || [[ ! ${3:-} =~ ^[1-5]$ ]]; then
                printf '%s\n' 'recover-attention-backlog requires cohort alignment|yt-dlp, limit 1..5, and optional --confirm RECOVER' >&2
                exit 64
            fi
            if (($# == 5)) && [[ ${4:-} != --confirm || ${5:-} != RECOVER ]]; then
                printf '%s\n' 'recover-attention-backlog mutation requires --confirm RECOVER' >&2
                exit 64
            fi
            run_preflight
            if (($# == 5)); then
                compose exec -T api python -m scripts.recover_attention_backlog --cohort "$2" --limit "$3" --confirm RECOVER
            else
                compose exec -T api python -m scripts.recover_attention_backlog --cohort "$2" --limit "$3"
            fi
            exit $?
        fi
        if [[ ${1:-} == diarization-canary ]]; then
            if (($# != 3)) || ! is_uuid "${2:-}" || [[ ${3:-} != --approved ]]; then printf '%s\n' 'diarization-canary requires exactly one UUID and --approved' >&2; exit 64; fi
            run_diarization_canary "$2"; exit $?
        fi
        if [[ ${1:-} == diarization-canary-recover ]]; then
            if (($# != 4)) || ! is_uuid "${2:-}" || ! is_uuid "${3:-}" || [[ ${4:-} != --approved ]]; then printf '%s\n' 'diarization-canary-recover requires video UUID, invocation UUID, and --approved' >&2; exit 64; fi
            recover_diarization_canary "$2" "$3"; exit $?
        fi
        if (($# != 2)) || [[ ${2:-} != --approved ]]; then printf '%s\n' 'maintenance requires an approved fixed action' >&2; exit 64; fi
        case "$1" in
            retire-disabled-profiles) run_retirement_preflight; run_compose --profile full --profile diarization rm --stop --force opensearch dashboards prometheus grafana diarization-worker ;;
            session-token-contract-drain) run_preflight; run_compose stop api worker analytics-retention summary-refresher archive-intelligence-refresher archive-enrichment-queue diarization-worker ;;
            session-token-contract-inspect) run_preflight; run_compose exec db psql -v ON_ERROR_STOP=1 -U postgres -d transcripts -c 'SELECT pid, usename, application_name, state, wait_event_type, query_start, xact_start, left(query, 120) AS query FROM pg_stat_activity WHERE datname = current_database() AND pid <> pg_backend_pid() ORDER BY xact_start NULLS LAST, query_start NULLS LAST;' ;;
            session-token-contract-migration) run_preflight; run_compose run --rm -e ALLOW_SESSION_TOKEN_CONTRACT_MIGRATION=true -e ALLOW_EVENT_TOKEN_CONTRACT_MIGRATION=true migrations ;;
            session-token-contract-verify) run_preflight; run_compose exec db psql -v ON_ERROR_STOP=1 -U postgres -d transcripts -c "SELECT version_num = '20260807_event_token' AS at_expected_head FROM alembic_version; SELECT NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema = 'public' AND table_name = 'sessions' AND column_name = 'token') AS hash_only_sessions; SELECT NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema = 'public' AND table_name = 'events' AND column_name = 'session_token') AS token_free_events; SELECT 1 / CASE WHEN (SELECT version_num = '20260807_event_token' FROM alembic_version) AND NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema = 'public' AND table_name = 'sessions' AND column_name = 'token') AND NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema = 'public' AND table_name = 'events' AND column_name = 'session_token') THEN 1 ELSE 0 END AS verification_must_be_1;" ;;
            pitr-base-backup) run_preflight; run_compose exec backup /scripts/walg_base_backup.sh ;;
            pitr-switch-wal) run_preflight; run_compose exec db psql -v ON_ERROR_STOP=1 -U postgres -d transcripts -c 'SELECT pg_switch_wal();' ;;
            pitr-archive-status) run_preflight; run_compose exec db psql -v ON_ERROR_STOP=1 -U postgres -d transcripts -c 'SELECT archived_count, failed_count, last_archived_wal, last_archived_time, last_failed_wal, last_failed_time, stats_reset FROM pg_stat_archiver;' ;;
            pitr-list-backups) run_preflight; run_compose exec backup wal-g backup-list ;;
            diarization-role-check) run_preflight; check_diarization_role ;;
            *) printf '%s\n' 'maintenance requires an approved fixed action' >&2; exit 64 ;;
        esac
        ;;
    config)
        shift
        if (($# != 1)); then printf '%s\n' 'config requires exactly one safe selector' >&2; exit 64; fi
        case "$1" in --quiet|--services|--profiles|--images) ;; *) printf '%s\n' 'config requires exactly one safe selector' >&2; exit 64 ;; esac
        run_compose config "$1"
        ;;
    ps|logs|top|images|version) shift; run_compose "$command" "$@" ;;
    up|down|pull|build|create|start|restart|stop|rm|run|exec|kill) printf '%s\n' "refusing unguarded state-changing command: $command; use deploy or maintenance" >&2; exit 64 ;;
    *) usage; exit 64 ;;
esac
