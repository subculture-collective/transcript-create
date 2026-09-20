# Generic core and client branding

1. Neutral default identity, artwork, UI text and processing prompts. Preserve persisted identifiers and historical migrations. Verify rendered surfaces.
2. Strict, versioned client profile loaded at startup: identity, operator, assets, light/dark colors and font preset. Existing SITE_* variables override profile identity. Invalid profiles fail startup. Verify API allowlist, frontend fallback/theme switching, server passage cards.
3. Separate deployments use unchanged core images plus mounted profiles/assets. Add a deterministic planner for per-client digest-pinned Compose overrides from verified release manifests. Preserve client files; no deployment side effects. Test multiple clients and invalid manifests/profiles.
4. Run backend, frontend, contract and browser checks including passage sharing, community and clip boundaries. Record actual evidence and limitations.

Assumption: independent deployments sharing releases; no multi-tenant data/auth changes. Existing runtime deployments are not updated by this implementation.

## Delivered and verified

Implemented all four units. See `docs/deployment/client-branding.md` for setup, supported profile tokens, migration and fleet update planning.

- Complete `scripts/verify.sh`: exit 0, 1,882 backend tests passed; 307 frontend passed/one existing skip; 21 Chromium browser tests passed. Configured lint/format/type/security, contract, build and bundle gates passed.
- Final Support copy spacing and generic project-label adjustment: five focused Support/branding tests passed after the full run.
- Actual local API on a disposable database plus Vite browser: Northstar identity, assets, About, Support, theme toggle and mobile navigation verified. No real OAuth sign-in, social post, payment, media ingestion or inference request made.
- CLI planner generated a synthetic digest-pinned release override and `docker compose config --quiet` accepted it. Unit tests exercise two clients, profile preservation, overwrite refusal, missing assets and fail-closed invalid input. Synthetic digests are not published or deployable release evidence.
- Evidence: `output/verification/client-branding/verify.log`; screenshots in `output/playwright/northstar-*`. Verification used Python 3.11.15 and the host Node 26.8.1; the CI-prescribed Node 20 matrix was not rerun locally. GPU images and live client deployments were not changed or requalified.
- Implementation prepared on `codex/passage-sharing`. No push or production deployment performed. Real client inventory is still needed to enroll existing implementations; this change supplies the common-core configuration and release-planning mechanism.
