# Passage sharing

**Status:** shipped product contract (2026-09-19).

Passage sharing lets a visitor choose a timestamp range, preview it in the source player,
and share a same-site link with transcript context. The basic workflow does not create a
database record, require an account or copy source media.

## User workflow

1. Choose **Share passage** on a search result or transcript selection.
2. Adjust the start and end using seconds, `HH:MM:SS.mmm`, the current playback
   position, or adjacent transcript segments.
3. Preview bounded playback and inspect the highlighted transcript with surrounding
   context.
4. Copy the passage link or invoke the browser's native share sheet.
5. Open the link in another session to restore the range and context.

The editor rejects malformed, reversed, missing-start and known-out-of-duration ranges.
Invalid ends are not silently clamped. Recordings without duration metadata cannot have
their upper bound verified. Large selections preserve their full time range while limiting
rendered selected segments to 200 and explaining the omission.

## URL and playback contract

An editable link uses this shape:

```text
/v/{videoId}?t=1108&t_ms=1108670&end_ms=1120530#moment-1108670
```

The existing `t` value keeps old start-only links compatible. `t_ms` carries the precise
start and `end_ms` adds the exclusive end. The URL contains no transcript text,
credentials or sender identity. It points to the currently available source and
transcript; it is not an immutable archive.

The player queues a preview until the YouTube API is ready, loads the bounded range with
`loadVideoById`, and clears the pending preview after an ordinary seek or pause. YouTube
starts can be approximate, so this is not a frame-accurate clip editor. See the
[YouTube IFrame API](https://developers.google.com/youtube/iframe_api_reference) and
[Web Share API](https://developer.mozilla.org/en-US/docs/Web/API/Navigator/share).

## Public passage pages

When `PUBLIC_PASSAGES_ENABLED=true`, `/api/share/videos/{videoId}` renders a public page
with title, range, excerpt metadata, an embedded player, a 1200 by 630 PNG card, and a
link back to the editable range. Reads bypass transcript and video caches, and responses
use `no-store` so deleting a source prevents future application responses. External social
platform caches cannot be recalled. Set the flag to false for private deployments.

Downloadable media clips are a separate feature requiring an authorized source,
source-transcript alignment, rendering, access controls, retention and expiry. Transcript
exports do not produce video clips.

## Verification

Frontend tests cover URL round trips, input validation, range hydration, transcript entry
points, adjacent extension, playback boundaries, delayed API readiness, clipboard and
native-share failures, and bounded long-selection rendering. Backend tests cover public
page feature gating, source removal, no-store responses and PNG card generation. The
seeded browser suite covers the user-facing archive journey; live social unfurls and
platform cache behavior require deployment-specific checks.
