# Creator publishing and passage community

Local implementation, disabled by default (`COMMUNITY_ENABLED=false`). Apply Alembic head before enabling. This release does not deploy anything or provision AT accounts.

## User journeys

- Creator administrator: Community → write text → Save draft → My posts → Publish publicly. Only administrators can create updates or pin root posts.
- Author editing: My posts → Edit post → Save draft edit. Publishing remains a separate action. Public edits explicitly say they take effect immediately. Edits require the displayed revision; a concurrent change returns a conflict and preserves the typed text. Authors cannot edit hidden posts around moderation.
- Combined timeline: published creator updates and root passage discussions appear alongside completed recordings with transcript segments. Drafts, hidden posts, and replies are excluded. Archive dates represent entry creation, not recording/broadcast dates. Pagination and source links are retained; publishing from this view refreshes it immediately.
- Member: select a transcript passage → Discuss passage → review source/range → save draft or publish publicly. Signed-in members can reply to published root posts.
- Moderator: Reports → decision reason → Hide/Restore → Resolve. Hidden posts also have a dedicated queue. Hiding a root suppresses its entire discussion from public reads. Reports are private to moderators; reporter identity is not exposed in the queue.
- Author: Export my posts downloads paginated JSON including drafts/hidden content; Delete post and replies requires an explicit browser confirmation. Account deletion removes authored community content, reports, and dependent replies. Account merges preserve authorship and deduplicate reports while preserving open review state.

Site publishing uses the existing session account and CSRF protections. AT identity is not inferred from a supplied handle, DID, or email. Site roles never grant power over an external repository. Local actions do not publish to Bluesky.

## Data and operating contract

New tables: `community_posts`, `community_reports`. Source-video deletion cascades to its discussions. Public feeds are bounded and paginated; author export and moderation queues are separate authorization boundaries. Per-account submissions serialize under a database row lock, with a ten-per-minute creation limit. Existing request limiting remains in place. Moderation reasons and actions are audited in the same transaction. Text is rendered as text, with no HTML/Markdown execution.

A migration rollback drops community tables and their content; export/backup must precede a real downgrade. Disable the feature to hide entry points/endpoints without deleting data. This is community-management software, not a staffed moderation service. Deployment needs an operator, escalation rules, policy review and retention/backup procedures. No private/paid community or federation guarantee is implied.

## Verification

Backend route and authorization tests cover publishing, revision conflicts, moderation,
account export and deletion. Frontend tests cover the creator, member and moderator
journeys. The seeded browser suite exercises the public timeline and passage workflow.
Run the canonical repository gate described in [testing](../development/testing.md)
before enabling the feature in a client deployment.
