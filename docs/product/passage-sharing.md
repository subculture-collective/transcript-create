# Passage sharing: first Recollect implementation

Updated September 19, 2026. Local implementation on `codex/passage-sharing`, based on deployed HasanAra source `311ddbe3df474b967e46409bc22218c3df49c119`. This change has not been deployed.

## Product boundary

This implements the first archive-sharing workflow from the Recollect proposal: find a passage, adjust its time range, preview the source, and share a same-site link with surrounding transcript context. It does not require a new account, database record, paid inference, or media acquisition.

The proposal source was read on Soyuz at `/Users/onnwee/Documents/Codex/2026-09-19/ho/outputs/HasanAra-Proposal/08 Research/Moment Sharing and Clip Export.md`, together with Current State, Decision Memo, Research Index, and Creator Community and AT Protocol. The user clarified that this task should build the first product phase in code rather than update those research notes.

## Available workflow

1. Choose **Share passage** on a search result, or select a transcript sentence/paragraph and choose **Share passage** in its actions.
2. The editor starts with that result's or selection's start and end. Enter seconds or `HH:MM:SS.mmm`, use the current playback position for either boundary, or include the previous/next transcript segment.
3. Inspect the duration and highlighted text with preceding/following context. Highlighting identifies overlapping transcript segments, not an exact word-level edit. Large selections render at most 200 selected segments plus context, with an explicit omission notice; their full time range remains in the link.
4. **Preview passage** requests bounded playback in the existing YouTube player. Repeat it to replay. **Continue after passage** seeks to the end and resumes ordinary playback.
5. **Copy passage link** copies the edited range. Browsers supporting native sharing also expose **Share passage**. If copying fails, the read-only link field supports manual selection/copy. Cancelling native sharing does not copy automatically or claim that a post was published.
6. Opening the copied URL in a fresh session restores the range editor and transcript context. Selecting another transcript moment returns to ordinary timestamp navigation.

## URL and state contract

Example: `/v/{videoId}?t=1108&t_ms=1108670&end_ms=1120530#moment-1108670`.

The existing start-only URL remains unchanged. `t_ms` carries precise starts; `end_ms` adds an exclusive end boundary. A malformed, reversed, missing-start, or known-out-of-duration range displays a validation error and cannot be previewed or shared. Invalid end times are not silently clamped. A recording whose duration is unavailable cannot have its upper bound verified from metadata.

Editor changes are drafts until copied/shared; the displayed passage link always reflects valid edits. No text, credentials, or sender identity are embedded in the URL. Links refer to the currently available source and transcript; they do not preserve an immutable copy or guarantee that a removed source will remain playable.

The editor owns draft input and sharing feedback. VideoPage owns navigation and the player reference. The player queues preview requests until readiness, uses the official object form of `loadVideoById` with start/end seconds, and clears the pending preview on an ordinary seek or pause. Existing transcript auto-scroll is suppressed while the passage editor is open so it cannot scroll past the editor on arrival.

Official API references checked September 19, 2026: [YouTube IFrame API](https://developers.google.com/youtube/iframe_api_reference) and [Web Share](https://developer.mozilla.org/en-US/docs/Web/API/Navigator/share). YouTube playback starts can be approximate; this is not a frame-accurate clip editor. Seeking after a bounded load cancels the endpoint according to the YouTube API contract.

## Verification

- Frontend tests cover precise URL round trips, malformed input, old links, fresh-session range hydration, transcript entry points, adjacent extension, playback boundaries, delayed player readiness, clipboard denial, native-share cancellation, and bounded rendering for long selections.
- Final checks passed: `npm test -- --run` (288 passed, one existing skip, 52 test files), `npm run build`, `npm run lint`, and `git diff --check`. Commands ran in `frontend` except the Git check.
- Browser checks exercised local Chromium at desktop, 390 × 844 portrait, and 844 × 390 landscape. Edited preview boundaries and continue-watching calls were read back from a player test double. Copied-link reopening and invalid-range disabled states were checked. Portrait and landscape document width matched viewport width.
- Browser data was synthetic and API calls were intercepted. The checks establish local UI behavior and player API arguments, not live YouTube playback accuracy, real mobile share-sheet behavior, production health, or deployed functionality.
- Local browser screenshots and snapshots are saved under `output/playwright/passage-sharing-20260919/cli`. The setup initially attempted a headed browser without an X server, then used headless Chromium. Initial requests before fixture interception failed against the absent local API; the subsequent fixture-backed interactions completed. No production API was used.
- Existing YouTube script-loading test remains skipped because the unit-test DOM cannot load that external script.

## Remaining stages

Per-selection social cards are not implemented here: the SPA still serves its existing generic social metadata. Before calling the sharing feature complete for a particular social destination, add server-readable title/range/excerpt metadata, define public-source eligibility and caching/deletion behavior, and check actual unfurls on the selected platforms. Client-side metadata changes alone would not prove crawler support.

Downloadable clips require a separately authorized source, source/transcript alignment checks, rendering, access controls, retention, costs, and expiry. The current Export menu continues to export transcripts, not video clips.

Existing-account AT Protocol OAuth, creator publishing, public passage discussions, moderation, and optional PDS hosting belong to subsequent phases. No new identities, social posts, hosted accounts, billing, or production services are introduced by this change.
