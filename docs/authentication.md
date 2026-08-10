# Authentication and accounts

HasanAra supports Google and Twitch OAuth sign-in. There is no password registration, password reset, automatic email-based account merging, or provider access-token persistence. A HasanAra account may link one Google and one Twitch identity; the immutable provider subject, not email, identifies an external account. If the two identities were used to create separate HasanAra accounts, the signed-in user may explicitly merge them after proving control of the second provider again.

## Provider setup

### Google

Create an OAuth 2.0 **Web application** client in Google Cloud Console. Configure exactly one callback for each deployment:

- Local: `http://localhost:8000/auth/callback/google`
- Production: `https://api.example.com/auth/callback/google` (replace `api.example.com` before deploy)

Google uses OpenID Connect scopes `openid email profile`. HasanAra uses the verified OIDC `sub` claim as the identity key; email is profile metadata only. Do not enable the obsolete Google+ API instruction.

### Twitch

Register an application in the Twitch Developer Console and configure its OAuth redirect URL:

- Local: `http://localhost:8000/auth/callback/twitch`
- Production: `https://api.example.com/auth/callback/twitch` (replace `api.example.com` before deploy)

Twitch requests the `user:read:email` scope and uses the Twitch user ID as its identity key.

Set the matching client ID, client secret, and redirect URI for each enabled provider. Keep client secrets outside tracked files.
Generate independent session and analytics secrets with `openssl rand -hex 32` for
each value; do not reuse either secret.

```dotenv
# Replace both documented placeholders with separate `openssl rand -hex 32` values.
# These placeholders are rejected in production.
SESSION_SECRET=SESSION_SECRET_PLACEHOLDER_REJECTED
ANALYTICS_HMAC_SECRET=YOUR_ANALYTICS_HMAC_SECRET_HERE
FRONTEND_ORIGIN=https://app.example.com
CORS_ALLOW_ORIGINS=https://app.example.com
OAUTH_GOOGLE_CLIENT_ID=
OAUTH_GOOGLE_CLIENT_SECRET=
OAUTH_GOOGLE_REDIRECT_URI=https://api.example.com/auth/callback/google
OAUTH_TWITCH_CLIENT_ID=
OAUTH_TWITCH_CLIENT_SECRET=
OAUTH_TWITCH_REDIRECT_URI=https://api.example.com/auth/callback/twitch
BOOTSTRAP_ADMIN_IDENTITIES=
```

Production requires HTTPS frontend origins and HTTPS provider callbacks. `FRONTEND_ORIGIN` is the default allowed CORS origin; `CORS_ALLOW_ORIGINS` can add explicit origins but must not use wildcards or local origins in production. Session cookies are HttpOnly and Secure in production, with `SameSite=Lax`.

For the HasanAra production host, put the redirect URIs in the deployment-only
`.env.prod` and use only the guarded immutable release helper described in the
[private-beta deployment runbook](deployment/private-beta.md):

```bash
scripts/compose_prod.sh preflight
scripts/compose_prod.sh deploy
```

Do not substitute raw Compose commands or the generic
`docker-compose.prod.yml`/Watchtower path on that host. The helper clears
inherited shell variables before loading `.env.prod`. The release overlays
require both `OAUTH_GOOGLE_REDIRECT_URI` and `OAUTH_TWITCH_REDIRECT_URI`; they
intentionally have no callback defaults. `BOOTSTRAP_ADMIN_IDENTITIES` remains
optional and may be empty.

## OAuth and session security

Start sign-in with `GET /auth/login/google` or `GET /auth/login/twitch`. Each redirect creates a server-side PostgreSQL OAuth-request record. State and, for Google, nonce bindings are provider- and intent-bound, expire after ten minutes, and are consumed once. The Authlib cookie only supports protocol compatibility; it is not authoritative state.

Successful sign-in creates or reuses the account for that provider subject. HasanAra never merges accounts by matching email. Provider tokens are used only for the exchange and are not persisted.

Session cookies contain an opaque raw token, but the database stores only its SHA-256 hash. `GET /auth/me` keeps the compatibility envelope and also returns the resolved `role` and `capabilities`; `GET /auth/csrf` returns a token bound to the active session.

Cookie-authenticated unsafe requests (`POST`, `PUT`, `PATCH`, and `DELETE`) require an allowed `Origin` and `X-CSRF-Token` header. In production, a missing Origin is rejected. API-key-only requests remain usable without a browser cookie. `POST /auth/logout` also enforces the allowed Origin and clears the current cookie.

## Account APIs

All account endpoints require authentication. Cookie-authenticated mutations also require the CSRF checks above.

- `GET /account` returns the profile, linked identities, and active sessions.
- `PATCH /account` updates the display name (1–100 trimmed characters) and optional absolute HTTPS avatar URL.
- `GET /account/identities` lists linked provider metadata; subjects and tokens are never returned.
- `POST /account/identities/{provider}/link` starts a link flow and returns an `authorization_url`; the callback returns to the account page.
- `POST /account/identities/{provider}/merge` starts a fresh OAuth proof for an explicitly confirmed merge after an ownership collision.
- `DELETE /account/identities/{provider}` removes a linked identity, except the final login identity cannot be unlinked.
- `GET /account/sessions` lists active sessions without tokens or token hashes.
- `DELETE /account/sessions/{session_id}` revokes one session; `DELETE /account/sessions?keep_current=true` revokes other sessions, and `keep_current=false` revokes all sessions and clears the cookie.
- `DELETE /account` requires JSON `{ "confirmation": "DELETE" }`, revokes account sessions and API keys, deletes private account data, and clears the cookie.

Linking requires an authenticated session both before redirect and at callback. If an identity is already linked to another account, the callback redirects to `/account?error=identity_conflict&provider=<provider>`; neither account is changed until the user chooses the explicit merge action and completes a second provider OAuth flow.

During a merge, the currently signed-in account remains canonical. The absorbed account's identities, saved moments, search history, vocabularies, non-conflicting saved searches, and job ownership move to it. For duplicate saved-search queries, the canonical account's existing definition wins. Job deduplication fields are cleared only where transferring ownership would violate an active uniqueness constraint. The higher role and non-free entitlement are preserved. Sessions for both accounts are revoked and replaced with one new session; API keys belonging to the absorbed account are deleted. The operation is one transaction and never uses email as proof of identity.

## Roles and administration

Authorization roles are `user`, `moderator`, and `admin`. Plans (including `pro`) are entitlements and are not roles. `PUT /admin/users/{user_id}/role` is admin-only and accepts one of those role values. The final active admin cannot be demoted or deleted.

Administrators may be bootstrapped with `BOOTSTRAP_ADMIN_IDENTITIES`, a comma-separated list of immutable `provider:subject` values such as `google:1234567890`. While an identity remains configured, every verified sign-in for that provider subject reasserts its `admin` role. Remove the identity from configuration before demoting it. `ADMIN_EMAILS` is retired, and email never grants runtime privileges.

## Deletion and retention

Deleting an account removes private account data, linked identities, sessions, and API keys. Archive records remain. Operational audit and event history is retained with account references anonymized (`user_id` becomes null), so retained records cannot identify the deleted account.

## Secret rotation and rollout

To rotate a provider secret: create a new secret at the provider, deploy it through the secret store, validate sign-in, then revoke the old secret. Rotating `SESSION_SECRET` does not invalidate opaque database sessions, because session lookup uses the raw token's database hash independently of that secret. It invalidates session-bound CSRF tokens and can disrupt in-progress OAuth compatibility cookies, so users may need to reacquire CSRF tokens or restart sign-in. To force a global logout, revoke or delete the session records.

The expand identity/session schema and the later plaintext-session removal require an atomic maintenance rollout. Do not run old and hash-only session consumers concurrently; drain old API writers, migrate and validate, deploy the converted consumers, complete the contract migration, then reopen traffic. Rolling back after hash-only sessions requires invalidating sessions because raw tokens cannot be reconstructed from hashes.

## Errors

Unauthenticated endpoints return `401`; insufficient authorization returns `403`. OAuth link identity collisions redirect to `/account?error=identity_conflict` rather than returning `409` from the callback. `409` applies to direct account mutation and domain conflicts where applicable, such as trying to unlink the final login identity or remove the final active admin. OAuth state, nonce, provider, or link-session failures are rejected without exposing provider credentials or tokens.
