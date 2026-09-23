# Client branding and shared core updates

**Status:** Implemented for separate client deployments. This is a configuration and release-planning workflow; it does not automatically deploy to existing installations.

## Ownership

Keep application code in this repository. Keep each client's public `brand.json`, assets, private environment, deployment topology and release history in that client's deployment directory or configuration repository. Each client has its own database, sessions, storage, origin and OAuth registrations. This does not introduce multi-tenant authentication or data routing.

One tested core release can serve all clients. Never edit React components, compiled bundles or upstream Git history to customize a client. Changes to the profile require restarting the API/application roles and reloading the browser; frontend rebuilding is unnecessary.

## Configure a client

Copy [the Northstar example](../../config/branding/northstar.json) and [its assets](../../config/branding/northstar-assets). Set `SITE_PROFILE_PATH` to an absolute path readable by the API and every Python application role. The file is validated at process startup; a missing file, unsupported schema, unknown field, unsafe URL or invalid color fails startup.

The HasanAra profile is [`config/branding/hasanara.json`](../../config/branding/hasanara.json), with assets in [`hasanara-assets`](../../config/branding/hasanara-assets). Its logo files are vector traces of the Piker Broadcasting Service mark: `logo.svg` (compact mark), `favicon.svg`, `badge.svg` (full TV badge with wordmark) and `social-card.svg`.

```bash
SITE_PROFILE_PATH=/absolute/path/to/client/brand.json .venv/bin/python -m uvicorn app.main:app --port 8000
VITE_API_PROXY_TARGET=http://localhost:8000 npm --prefix frontend run dev
```

For local Vite development, place client assets under `frontend/public/branding/` (ignored local files). The production planner mounts the asset directory at `/usr/share/nginx/html/branding` in Nginx. URLs like `/branding/logo.svg` then work in both environments. Missing production assets return 404 and client assets are revalidated, rather than cached as immutable application bundles.

| Profile fields | Purpose |
| --- | --- |
| `schema_version` | Must be `1`; defaults to 1 for compatible minimal profiles. |
| `name`, `description`, `creator_name`, `tagline` | Site identity, home copy, route titles and metadata. |
| `operator_name`, `operator_url`, `project_notice` | Operator attribution, About, Support and footer. Empty operator URL omits the link. |
| `logo_url`, `favicon_url`, `social_image_url` | Same-origin absolute paths or HTTPS asset URLs. |
| `theme.font` | Optional: `system`, `editorial` or `mono`. When omitted, the core typefaces (Newsreader and Inter Tight) apply. No executable CSS or arbitrary font URLs. |
| `theme.dark`, `theme.light` | Partial maps of semantic color tokens to six-digit hex colors. Omitted tokens use the core stylesheet. |

Supported tokens: `canvas`, `surface`, `surface-muted`, `surface-raised`, `border`, `border-strong`, `ink`, `muted`, `subtle`, `accent`, `accent-hover`, `accent-soft`, `accent-contrast`, `accent-2`, `accent-3`, `player-accent`, `cta`, `success`, `success-soft`, `warning`, `warning-soft`, `danger`, `danger-soft`. Set accent/contrast and background/ink pairs together and check contrast in both themes. `accent-2`, `accent-3` and `player-accent` form the three-colour stripe under the header and color data marks; they are decorative and need not meet text contrast. A profile without a theme keeps the Broadsheet colors. Theme switching retains the visitor's preference. Server-rendered passage pages and generated PNG cards use the client's dark canvas, ink and accent, falling back to the core night-edition colors.

The generated [JSON schema](../../config/branding/schema.json) describes the complete public profile. Do not store passwords, OAuth credentials, private URLs, feature entitlements or arbitrary HTML in it. `/api/site` exposes only public profile fields and the existing explicit feature flags. Those flags remain server environment settings.

Existing `SITE_NAME`, `SITE_DESCRIPTION` and `SITE_CREATOR_NAME` environment values take precedence over corresponding file values. Remove those variables when the profile should own identity. Defaults are neutral if no profile is selected or if the frontend cannot fetch configuration. The static SPA HTML is neutral before JavaScript loads; client metadata updates after `/api/site` loads. Public passage pages render their identity and metadata on the server for crawlers.

## Update all branded implementations

Use the existing release pipeline and its verified, digest-pinned manifest (`schema_version`, `source_commit`, `images`, `services`). The planner intentionally consumes the existing release contract rather than accepting mutable `latest` tags or inventing a new image pipeline.

Create a fleet file following [the example](../../config/branding/fleet.example.json). Paths resolve relative to the fleet file. List every application service used by each deployment; `api`, `frontend` and `migrations` are required, and the other services must match the existing release manifest's service map. The existing manifest currently describes the CUDA role family; other accelerator topologies need their own qualified release contract rather than relabeling an image.

```bash
.venv/bin/python scripts/plan_client_updates.py \
  --manifest /path/to/verified-release-images.json \
  --fleet /path/to/clients/fleet.json \
  --output /path/to/updates/release-2026-09-19
```

The planner validates the entire inventory before creating output, refuses to overwrite an existing output directory, and writes:

- `plan.json`: exact core commit, release-manifest checksum and each client's profile checksum.
- `<client>.compose.json`: pinned images plus read-only profile and frontend-asset mounts. Client profiles, secrets, assets and databases are never edited.

Review these overrides against each client's actual Compose service set. Add the client override **last** in that client's existing Compose file list. It is an overlay, not a standalone stack. The existing private environment and infrastructure configuration remain deployment-owned. Use `docker compose config --quiet` to validate the combined model without printing secrets. Do not pass `--build`; consume the verified image digests.

Qualify the release on one client's staging instance, take and verify that client's normal database backup, run its migration/preflight process, then roll out the same manifest to the remaining clients in batches. Verify `/api/site`, login, search, passage sharing and client assets per deployment. Record running image digests against `plan.json`. Profile checksums must still match the plan; regenerate if a profile changed. This planner does not replace release signature, backup, migration or application-health checks.

For rollback, retain the previous image override, profile and asset revision, and database recovery evidence. Image rollback alone is insufficient after an incompatible schema migration. No existing client is enrolled or remotely updated until its real inventory is supplied.

## Migrating a formerly branded checkout

Set an explicit client profile before upgrading an existing branded deployment, including its existing operator attribution and artwork. Keep its existing database and secret environment. The old internal storage keys, advisory-lock identifiers, migration history and release-image variable names are retained for compatibility; they are not the displayed brand.

The base no longer injects a creator-specific Whisper prompt or curated political periods/topics. Existing stored recordings, topics and periods are preserved. A deployment that intentionally uses the old editorial dataset can set `ARCHIVE_EDITORIAL_PRESET=hasanara` and supply its original `WHISPER_INITIAL_PROMPT` explicitly. New clients default to `generic`; editorial curation then comes from their own archive/admin data. No inference calls, backfills or data deletions are performed by changing the presentation profile.

## Verification

```bash
.venv/bin/python -m pytest tests/test_branding.py tests/test_site.py
npm --prefix frontend run test -- --run
PLAYWRIGHT_PORT=55173 npm --prefix e2e run test:critical -- --workers=4
```

Backend passage, community and clip-export tests also require the disposable database described in [testing](../development/testing.md). The canonical `make verify` covers the broader repository checks. Use a dedicated `PLAYWRIGHT_PORT` when another app uses 5173.
