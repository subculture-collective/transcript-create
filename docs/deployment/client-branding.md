# Client branding and shared core updates

**Status:** Implemented for separate client deployments (updated 2026-10-03 for the headless core). This is a configuration and release-planning workflow; it does not automatically deploy to existing installations.

## Ownership

Keep backend code in this repository. Keep each client's public `brand.json`, assets, frontend, private environment, deployment topology and release history in that client's deployment directory or configuration repository. Each client has its own database, sessions, storage, origin and OAuth registrations. This does not introduce multi-tenant authentication or data routing.

One tested core release can serve all clients. Core is headless: it ships no web pages and no frontend image. Each archive builds and deploys its own frontend, usually with the [`rekolekt-web`](https://git.subcult.tv/subculture-collective/rekolekt-web) kit, on an origin of its choosing. Set `FRONTEND_ORIGIN` on the API to that origin, such as `https://hasanara.tv`; the API uses it for CORS, CSRF and cookie settings. Changes to the profile require restarting the API/application roles.

## Link previews and artwork

The archive frontend owns its HTML, site metadata, link previews and static artwork, including the files that `logo_url`, `favicon_url` and `social_image_url` point to. The API only reports those URLs at `/site`. Server-rendered shared passage pages and their PNG cards come from the API and keep their own previews.

## Configure a client

Copy [the Northstar example](../../config/branding/northstar.json) and [its assets](../../config/branding/northstar-assets). Set `SITE_PROFILE_PATH` to an absolute path readable by the API and every Python application role. The file is validated at process startup; a missing file, unsupported schema, unknown field, unsafe URL or invalid color fails startup. Serve the assets from the archive frontend so the profile's `/branding/...` URLs resolve on its origin.

Client profiles and assets are not stored here. HasanAra's profile, artwork and production overlay are in its deployment repository, `subculture-collective/hasanara`.

```bash
SITE_PROFILE_PATH=/absolute/path/to/client/brand.json .venv/bin/python -m uvicorn app.main:app --port 8000
curl http://localhost:8000/site
```

| Profile fields | Purpose |
| --- | --- |
| `schema_version` | Must be `1`; defaults to 1 for compatible minimal profiles. |
| `name`, `description`, `creator_name`, `tagline` | Site identity for frontends, passage pages and metadata. |
| `operator_name`, `operator_url`, `project_notice` | Operator attribution and notices. Empty operator URL means no link. |
| `logo_url`, `favicon_url`, `social_image_url` | Same-origin absolute paths or HTTPS asset URLs, served by the archive frontend. |
| `theme.font` | **Deprecated in the API.** Optional: `system`, `editorial` or `mono`. No executable CSS or arbitrary font URLs. |
| `theme.dark`, `theme.light` | **Deprecated in the API.** Partial maps of semantic color tokens to six-digit hex colors. |

Supported tokens: `canvas`, `surface`, `surface-muted`, `surface-raised`, `border`, `border-strong`, `ink`, `muted`, `subtle`, `accent`, `accent-hover`, `accent-soft`, `accent-contrast`, `accent-2`, `accent-3`, `player-accent`, `cta`, `success`, `success-soft`, `warning`, `warning-soft`, `danger`, `danger-soft`.

### Deprecated theme fields

The `theme` object in the `/site` response (`SiteConfig.theme`, component `BrandTheme` with `font`, `dark` and `light`) is marked `deprecated: true` in [the OpenAPI contract](../api/openapi.json). It is still validated and served unchanged, so frontends that read it keep working. New frontends should own their typography and colors instead of reading them from the API. Removal would follow the [versioning policy](../api/versioning.md); none is scheduled.

The profile's `theme.dark` `canvas`, `ink` and `accent` tokens still color the server-rendered passage pages and PNG cards, falling back to the core night-edition colors. Keep them in the profile if you want those pages to match the archive.

The generated [JSON schema](../../config/branding/schema.json) describes the complete public profile. Do not store passwords, OAuth credentials, private URLs, feature entitlements or arbitrary HTML in it. `/site` exposes only public profile fields and the existing explicit feature flags. Those flags remain server environment settings.

Existing `SITE_NAME`, `SITE_DESCRIPTION` and `SITE_CREATOR_NAME` environment values take precedence over corresponding file values. Remove those variables when the profile should own identity. Defaults are neutral if no profile is selected. Public passage pages render their identity and metadata on the server for crawlers.

## Production deployment layout

A production client is a deployment repository. It pins this repository as a Git submodule at `core/`, checked out at a release's `source_commit`, and commits:

| Path | Purpose |
| --- | --- |
| `core/` | Submodule at the released core commit |
| `docker-compose.client.yml` | Client overlay: origins, OAuth callback requirements, host port bindings, external networks, channel sources, and profile mounts |
| `branding/brand.json`, `branding/assets/` | Public profile and assets, mounted read-only |
| `release-images.json` | The verified, digest-pinned release manifest being deployed |

The operator env file (`.env.prod`), diarization credentials and the state directories (`data/`, `cache/`, `backups/`, `docker-volumes/`, `deploy-backups/`) stay in the deployment directory and are ignored by Git.

`scripts/compose_prod.sh` requires `TRANSCRIPT_DEPLOY_ROOT` to name that directory. It uses the directory as the Compose project directory, so state paths resolve there, and passes `TRANSCRIPT_CORE_DIR` so core-owned paths (scripts, configuration, build contexts) resolve inside the submodule. Compose files are applied in this order: core `docker-compose.yml`, `docker-compose.gtx1080.yml` and `docker-compose.production.yml`, then the client overlay, then core `docker-compose.storage.yml`, `docker-compose.pitr.yml` and, last, `docker-compose.release.yml`. Run it from the deployment:

```bash
TRANSCRIPT_DEPLOY_ROOT="$PWD" core/scripts/compose_prod.sh preflight
```

Operator procedures elsewhere in this documentation write `scripts/compose_prod.sh`; run them the same way. The preflight requires clean core and deployment trees, a core `HEAD` equal to the manifest's `source_commit`, the client overlay, and every external network named in the rendered configuration. `docker-compose.production.yml` defines the shared production services the preflight enforces. The `hasanara` Compose project name, container names and database role names are retained compatibility identifiers used by the guarded maintenance actions; one host therefore runs one production client.

To update a client, advance the submodule to the new release's `source_commit`, replace `release-images.json` with that release's verified manifest, review the diff, commit, and run the deployment's normal preflight and deploy steps.

The core Compose files and release manifest define backend services only. The preflight accepts only the services in the manifest's service map, so run the archive frontend outside the `hasanara` Compose project (its own Compose project, host service or static hosting) and deploy it from the archive's own build. A deployment upgrading from a core release that still had a `frontend` service must first bring up its replacement frontend, then stop and remove the old container (named `hasanara-web` by the old production Compose file, for example with `docker rm -f hasanara-web`). The preflight rejects leftover project containers that the release does not define.

## Update all branded implementations

Use the existing release pipeline and its verified, digest-pinned manifest (`schema_version`, `source_commit`, `images`, `services`). The planner intentionally consumes the existing release contract rather than accepting mutable `latest` tags or inventing a new image pipeline.

Create a fleet file following [the example](../../config/branding/fleet.example.json). Paths resolve relative to the fleet file. List every application service used by each deployment; `api` and `migrations` are required, and the other services must match the release manifest's service map. `frontend` is no longer a core service. The existing manifest currently describes the CUDA role family; other accelerator topologies need their own qualified release contract rather than relabeling an image.

```bash
.venv/bin/python scripts/plan_client_updates.py \
  --manifest /path/to/verified-release-images.json \
  --fleet /path/to/clients/fleet.json \
  --output /path/to/updates/release-2026-09-19
```

The planner validates the entire inventory before creating output, refuses to overwrite an existing output directory, and writes:

- `plan.json`: exact core commit, release-manifest checksum and each client's profile checksum.
- `<client>.compose.json`: pinned images plus read-only profile mounts for the Python roles. Client profiles, secrets, assets and databases are never edited. The planner still checks that local `/branding/...` profile URLs exist in the client asset directory.

Review these overrides against each client's actual Compose service set. Add the client override **last** in that client's existing Compose file list. It is an overlay, not a standalone stack. The existing private environment and infrastructure configuration remain deployment-owned. Use `docker compose config --quiet` to validate the combined model without printing secrets. Do not pass `--build`; consume the verified image digests.

Qualify the release on one client's staging instance, take and verify that client's normal database backup, run its migration/preflight process, then roll out the same manifest to the remaining clients in batches. Verify `/site`, login, search, passage sharing and the archive frontend per deployment. Record running image digests against `plan.json`. Profile checksums must still match the plan; regenerate if a profile changed. This planner does not replace release signature, backup, migration or application-health checks.

For rollback, retain the previous image override, profile and asset revision, and database recovery evidence. Image rollback alone is insufficient after an incompatible schema migration. No existing client is enrolled or remotely updated until its real inventory is supplied.

## Migrating a formerly branded checkout

Set an explicit client profile before upgrading an existing branded deployment, including its existing operator attribution and artwork. Keep its existing database and secret environment. The old internal storage keys, advisory-lock identifiers, migration history and release-image variable names are retained for compatibility; they are not the displayed brand.

The base no longer injects a creator-specific Whisper prompt or curated political periods/topics. Existing stored recordings, topics and periods are preserved. A deployment that intentionally uses the old editorial dataset can set `ARCHIVE_EDITORIAL_PRESET=hasanara` and supply its original `WHISPER_INITIAL_PROMPT` explicitly. New clients default to `generic`; editorial curation then comes from their own archive/admin data. No inference calls, backfills or data deletions are performed by changing the presentation profile.

## Verification

```bash
.venv/bin/python -m pytest tests/test_branding.py tests/test_site.py
```

Backend passage, community and clip-export tests also require the disposable database described in [testing](../development/testing.md). The canonical `make verify` covers the broader repository checks, including the OpenAPI drift check. Browser tests belong to each archive frontend.
