# Recollect implementation ledger

User direction: implement the roadmap as far as possible, verifying and committing each coherent increment. Work remains local unless separately authorized. Preserve existing untracked deployment instructions, cleanup script, and browser evidence.

## Sequence and acceptance

| Increment | Acceptance | Status |
| --- | --- | --- |
| Passage selection | Search/transcript entry points, range editing, context, preview, reproducible links, failures handled | Committed `30228f5`; 288 frontend tests passed, one existing skip; build/lint and fixture browser checks passed |
| Public preview pages | Server-rendered range/title/excerpt metadata and PNG card, safe escaping, bounded reads, invalid/missing source rejection, same-site player/context destination | Committed `65e8ee9`; 22 backend checks, 39 frontend checks, build and actual embedded-player stop verified |
| Creator configuration | Reusable site name/description, public configuration, no customer claims or secrets exposed, default HasanAra preserved | Implemented; explicit public allowlist, 37 frontend tests and backend config test passed; build passed |
| Publishing/community | Public updates and passage discussions, explicit publishing, permissions, pagination, reports, local moderation/audit, export | Implemented; 1,837 fresh backend tests passed, 294 frontend tests passed/one skip; real local browser publishing and moderation passed. Full gate blocked by dependency audit; see `docs/product/creator-community.md` |
| Existing AT accounts | Official OAuth SDK, independent existing PDS support, explicit public standard records, no email-based identity merge | Opt-in standalone OAuth/public-post bridge implemented and locally checked; site identity linking, reply synchronization and live provider qualification remain open. See `docs/product/at-account-bridge.md` |
| Authorized-original clips | Acquisition separate from rendering, bounded local-original registration, queued render, retention/expiry/access checks, synthetic-media verification | Implemented opt-in local operator pipeline and owner-only UI/API; synthetic browser download verified. Production sandbox/scheduling and creator authorization remain gates. See `docs/product/authorized-original-clips.md` |
| Managed PDS | Assess existing Subcult PDS scripts, define and verify safe local preflight/export contracts; no account creation/migration/deployment | Pending; live restore/migration and recovery setup are external gates |

For each implementation increment run focused backend/frontend tests and relevant browser checks. Run broad backend verification against a disposable local PostgreSQL database after schema/shared contract changes. Regenerate OpenAPI and frontend types when API contracts change. Record actual commands, results, and remaining gaps below; do not treat mocks or a passing build as production proof.

## Reuse inventory

- HasanAra: FastAPI, PostgreSQL/Alembic, account roles, session/CSRF helpers, audit logs, React SPA, source-linked transcript and search flows.
- Patchwork: inspected `packages/at-client/src/oauth-client.ts`; official Node OAuth adapter wraps authorize/callback/restore/revoke. Different TypeScript runtime and domain model: reference patterns, not drop-in Python authentication.
- Subcult PDS: inspected README and source inventory. Pinned official PDS image, invite-only configuration, checksum-backed backup/restore scripts. SMTP is documented as unset, so password recovery is not established. No live hosting readiness claim follows from source inspection.

## External boundaries

No paid inference, new accounts, outreach, real social publishing, real-media acquisition, production writes, or account migration. Protocol Spaces remains alpha per official September 19 source inspection and is excluded from production private-community design. Commercial demand, creator authorization, staffing, pricing, and name clearance remain unresolved business decisions rather than code completion criteria.
