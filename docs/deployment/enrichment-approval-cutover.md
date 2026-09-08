# PR28 enrichment approval and legacy cleanup

User authorization on September 7 explicitly covers removal of older published
chapters as well as unreviewed candidates, approval of successful newer output,
and automatic approval of future successful runs. It does not authorize deleting
videos, transcripts, shared labels, deterministic assignments, costs or run history.

## Boundary and acceptance

Use generating-run `started_at`, not VOD date or the insufficiently granular v7
prompt label. The PR28 deployment began at `2026-09-07T00:30:07Z`; no paid attempt
crossed that deployment. Existing successful DeepSeek v7 runs after that boundary
are eligible for approval if their untouched candidates still satisfy publication
checks. Generation failures are never approved. Prior hidden/rejected/edited work
outside the explicitly authorized legacy cohort stays protected.

`ARCHIVE_ENRICHMENT_AUTO_APPROVE=true` enables a separate approval step after the
normal generation and stored-candidate quality checks. The direct generation
publication flag `ARCHIVE_ENRICHMENT_PUBLISH` stays false. Successful chapters use
the normal chapter-review validator and receive `published`; LLM assignments
receive `admin_approved`. Candidate labels referenced by these assignments become
published only if there is no editorial conflict or unrelated visible assignment
that this would expose. Existing published shared labels remain unchanged. Hidden
topic labels and their candidate assignments remain suppressed; publication records
their count and still requires at least one non-hidden sustained category. Rejected
or merged labels remain a blocking conflict.

Approval snapshots and ordinary review audit entries are committed in the same
transaction. An approval error rolls back candidate/publication writes and records
a failed attempt with measured usage. Approval is idempotent and cannot re-publish
a subsequently hidden item. Guarded canaries explicitly disable auto-approval.

## Maintenance procedure

1. Stop the worker, retain the durable failure-rate pause, and globally disable
   enrichment during deployment. Take and verify a fresh WAL-G backup, closing WAL,
   original release manifest, environment and rollback image.
2. Test, publish and qualify the immutable API image. Deploy with processing and
   auto-approval disabled; verify migration, core health and protected-data hashes.
3. Rehearse `python scripts/approve_archive_enrichment.py` from the pinned image.
   This executes the complete transaction and rolls back row mutations. Audit
   sequence gaps from rehearsal are expected; no provider is called.
4. With the worker stopped, apply using `--apply --approved`. Owner fencing,
   unresolved-running checks and row locks protect the atomic cleanup/approval.
5. Verify exact cohort counts, snapshots, public chapters/category visibility,
   surviving videos/transcripts/non-LLM assignments/shared-label identities, intact
   run/cost history and feedback, and no orphan/cascade deletions.
6. Persist `ARCHIVE_ENRICHMENT_AUTO_APPROVE=true` for future successful processing.
   Resume the existing provider/failure-rate pause only after the deployed provider
   envelope checks and publication gates pass, retaining an append-only recovery
   checkpoint. The user authorized deployment and restart on September 7.

Legacy cleanup snapshots every removed chapter and LLM assignment, plus affected
feedback with its original foreign keys, into `archive_enrichment_maintenance_rows`.
Feedback rows survive deletion with null target links; the snapshots preserve those
links for recovery. Explicitly superseded chapter feedback does not veto replacement
work, but subsequent feedback does. Out-of-scope dependent assignments halt cleanup
instead of being cascade-deleted. Original run records, retry budgets and costs are
never reset. Shared labels and aliases are not deleted. Re-eligible source videos
are discovered by the queue after processing is separately recovered.

Initial inventory: 21,979 older chapters (12 already published), 19,608 older LLM
assignments (including 10 previously approved), 1,084 newer candidate chapters across
32 videos and 657 newer candidate assignments. Revalidate immediately before apply;
these counts are evidence expectations, not broad delete criteria.

The separately completed one-video cleanup removed those 12 chapters and 10 LLM
assignments plus 421 deterministic assignments for that video only. Its verified
snapshot is `deploy-backups/one-video-generated-cleanup-iv4g522y` on Almaz. Remaining
legacy cleanup expectations are 21,967 chapters and 19,598 LLM assignments. Preserve
its 22 audit rows and recovery snapshot; no shared label was removed or unhidden.

Provider response repair: recognize error envelopes carried by HTTP-success
responses before looking for assistant content. Record only numeric error codes,
not raw messages or metadata. Empty/malformed response envelopes pause as provider
failures; code 402 pauses for credits. Preserve measured usage and never replay
an uncertain paid response. This corrects classification, not the upstream cause;
a renewed provider error must stop the resumed worker for diagnosis.

Rollback uses the fresh backup or explicit row-snapshot restoration in foreign-key
order under the same maintenance fence. Preserve approval/cleanup audit history;
do not delete failed ledgers, reset attempts, or overwrite old snapshots.
