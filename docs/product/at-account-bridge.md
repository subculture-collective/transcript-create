# Existing AT account bridge

Implemented locally as an optional standalone public-post composer; `ATPROTO_ENABLED=false` by default. `/at.html` is a separate browser document, entered through a full navigation. The main archive retains `connect-src 'self'`; only the OAuth document permits HTTPS connections to user-selected PDS/authorization hosts. No inline scripts are permitted.

## Contract

- Official `@atproto/oauth-client-browser` pinned at 0.5.7 handles provider discovery, PKCE, PAR, DPoP, callback validation, session storage/refresh and revocation. Inspected installed SDK types/source rather than relying on an older README: this version uses `onSessionDeleted`, `signInRedirect`, and `BrowserOAuthClient.load` for loopback metadata.
- Metadata is derived only from configured `FRONTEND_ORIGIN`, not Host headers. Production requires HTTPS without a custom port. Loopback metadata is allowed only outside production. Callback is exactly `/at.html`.
- Requests only `atproto repo:app.bsky.feed.post?action=create`. No identity, email, profile, private-message, blob, delete, or arbitrary-collection access is requested.
- Connection alone publishes nothing. The user reviews text/source and checks a destination acknowledgement before creating an `app.bsky.feed.post` record on the SDK session's own DID. Passages use `app.bsky.embed.external`. The SDK performs the authenticated XRPC call; application code does not construct OAuth tokens/DPoP proofs.
- Each attempted draft retains a record key during the page session, so a timed-out retry cannot create a second record. After an ambiguous response, users are directed to inspect the account before starting a different post. Reloading loses the local draft/attempt; it never triggers a write.
- A configured resolver receives handle/IP data; the UI discloses the resolver before redirect. Default is `https://bsky.social`; this can be changed to an operator-owned compatible resolver.
- OAuth storage is browser-managed, so shared devices need explicit disconnect/revocation. Archive logout and AT disconnect are separate operations and are labeled accordingly. No browser-supplied DID is accepted as Python session identity or as an archive role. Fresh server-side proof would be required to add AT-only site login/account linking.

## Verification and limits

Eight backend metadata/config checks and five frontend publishing tests passed; production build/lint/bundle budget passed (OAuth entry about 59 KiB gzip, separate from the archive). A real browser initialized the SDK from local loopback metadata and displayed the provider form. Mocked publishing checks prove explicit consent, fixed destination DID and stable retry keys, not successful live publishing. No external account was authorized and no social post was created.

Live callback, refresh/revocation, cross-provider compatibility, public record readback and AppView indexing remain qualification gates. Site threads are local; they do not synchronize AT replies or give AT-only users local membership. A production integration of site identity should use a confidential backend OAuth client/service and durable encrypted session storage. The current public client is deliberately limited to user-initiated external sharing. No custom Lexicon, AppView, managed PDS, migration, or private/paid community is included.

## Official sources checked September 19, 2026

- [OAuth profile](https://atproto.com/specs/oauth): discoverable metadata, loopback exception, DPoP and state requirements.
- [OAuth patterns](https://atproto.com/guides/oauth-patterns): federated discovery and action-scoped repository permissions.
- [Permissions](https://atproto.com/specs/permission): repository create permissions.
- [Official browser SDK](https://github.com/bluesky-social/atproto/tree/main/packages/oauth/oauth-client-browser): public-client model; backend confidential clients preferred for server-managed identity.

These sources inform the implementation boundary, not a claim that live provider behavior has been qualified.
