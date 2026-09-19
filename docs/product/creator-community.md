# Creator publishing and passage community

Local implementation, disabled by default (`COMMUNITY_ENABLED=false`). Apply Alembic head before enabling. This release does not deploy anything or provision AT accounts.

## User journeys

- Creator administrator: Community → write text → Save draft → My posts → Publish publicly. Only administrators can create updates or pin root posts.
- Member: select a transcript passage → Discuss passage → review source/range → save draft or publish publicly. Signed-in members can reply to published root posts.
- Moderator: Reports → decision reason → Hide/Restore → Resolve. Hidden posts also have a dedicated queue. Hiding a root suppresses its entire discussion from public reads. Reports are private to moderators; reporter identity is not exposed in the queue.
- Author: Export my posts downloads paginated JSON including drafts/hidden content; Delete post and replies requires an explicit browser confirmation. Account deletion removes authored community content, reports, and dependent replies. Account merges preserve authorship and deduplicate reports while preserving open review state.

Site publishing uses the existing session account and CSRF protections. AT identity is not inferred from a supplied handle, DID, or email. Site roles never grant power over an external repository. Local actions do not publish to Bluesky.

## Data and operating contract

New tables: `community_posts`, `community_reports`. Source-video deletion cascades to its discussions. Public feeds are bounded and paginated; author export and moderation queues are separate authorization boundaries. Per-account submissions serialize under a database row lock, with a ten-per-minute creation limit. Existing request limiting remains in place. Moderation reasons and actions are audited in the same transaction. Text is rendered as text, with no HTML/Markdown execution.

A migration rollback drops community tables and their content; export/backup must precede a real downgrade. Disable the feature to hide entry points/endpoints without deleting data. This is community-management software, not a staffed moderation service. Deployment needs an operator, escalation rules, policy review and retention/backup procedures. No private/paid community or federation guarantee is implied.

## Verification, September 19, 2026

- Fresh isolated PostgreSQL/Redis/OpenSearch, full migration history: 1,837 backend tests passed, 82.61% application coverage. Migration/bootstrap parity includes the new tables and user FKs.
- Frontend: 294 passed, one existing skip. Build and lint passed during the increment.
- Real browser/local API: configurable branding, draft → publish → persisted reply, report → hide → restore → resolve, mobile width without horizontal overflow. All accounts/content were synthetic local fixtures.
- Full `scripts/verify.sh` stopped after backend/security analysis at dependency audit. Existing AnyIO 4.14.0, Lightning 2.6.5 and PyTorch 2.12.1 findings require dependency qualification; Lightning/PyTorch exceptions expired September 13. No exceptions were extended.
- A subsequent focused run accidentally targeted the browser-seeded fixture database; its assumptions of an empty feed/only test-created admins failed. The fresh complete run above is the authoritative backend result. Keep browser fixtures and unit/integration databases separate.
