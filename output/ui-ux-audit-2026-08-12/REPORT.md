# HasanAra UI/UX audit — deployed `v0.1.0-rc.6`

Date: 2026-08-12  
Primary browser: Google Chrome 151  
Primary viewport: 390 × 844 CSS px, touch enabled, 3× device scale  
Additional viewports: 768 × 1024 and 1440 × 1000  
Build audited: `acc358b6b4d21f4f903cbda99f3ddd118ec940cc`

## Executive verdict

HasanAra has a distinctive editorial identity and an unusually valuable content model, but the mobile product is still shaped like a responsive desktop research application. The strongest user value—moving fluidly among a feed, a source video, and cited transcript text—is not expressed by the interface hierarchy.

The central mobile failure is not merely that the video is physically small. It is that video has no persistent spatial or interactional authority. On a 390 × 844 viewport, the player begins 728 px into the episode page, below a 358 px masthead and two empty intelligence panels. It is 356 × 200 px, occupies 23.7% of the viewport height, and immediately scrolls away. The transcript begins at 1,748 px. Tapping a transcript sentence seeks a now-invisible player. This separates cause (the source video) from evidence (the transcript) and makes the core interaction feel like a desktop document viewer squeezed into a phone.

The VOD feed has the same underlying problem. Filters, metrics, and pagination consume 771 px before the first result. A 24-card page is 9,852 px tall, and the first viewport shows only a sliver of one result card. The cards are visually large but informationally weak: generic date-based titles, duplicated dates, repeated channel names, and no topical reason to choose one VOD over another.

The right redesign is a mobile media-research product with a persistent player and a transcript bottom sheet, paired with a compact, topic-rich feed—not smaller spacing applied to the current desktop composition.

## Scope and method

- 33 route/viewport examinations across 11 routes.
- 34 full-page screenshots plus seven focused mobile screenshots.
- Live production data, production frontend image, and immutable release digests.
- Chrome accessibility trees, console output, failed requests, headings, landmarks, labels, IDs, overflow, control geometry, text sizing, and layout-shift observation.
- Real journeys: home search, result-to-VOD, theme switch, mobile navigation, feed-to-VOD, browser Back, transcript sentence selection.
- 33 axe-core scans against WCAG 2 A/AA, WCAG 2.1 A/AA, WCAG 2.2 AA, and best-practice rules in mobile light, mobile dark, and desktop light profiles.
- Source review of the route architecture and current component/layout contracts.

The external invite screen was bypassed only by reaching the production containers on their host bindings. Browser `/api` requests were transparently forwarded to the production API because the frontend container intentionally relies on the external reverse proxy for `/api` routing.

## Product scorecard

| Dimension | Score | Assessment |
| --- | ---: | --- |
| Product concept | 9/10 | Citation-first VOD research is differentiated and coherent. |
| Editorial visual identity | 7/10 | Memorable typography and archival voice; sometimes over-applied. |
| Desktop information architecture | 7/10 | Deep and capable, though action-heavy. |
| Mobile feed | 3/10 | Low information scent, excessive preamble, slow scanning. |
| Mobile episode/watch experience | 2/10 | Player is delayed, transient, and disconnected from transcript actions. |
| Search usability | 5/10 | Strong evidence model, but dense actions and inaccessible highlights. |
| Accessibility | 5/10 | Good labels/headings baseline; severe highlight contrast and route-focus defects. |
| Perceived performance | 4/10 | Large asynchronous shifts and thousands of mounted transcript controls. |
| Navigation continuity | 4/10 | Back restoration works, but forward scroll/focus/title behavior is accidental. |
| State communication | 6/10 | Empty states exist; some empty intelligence displaces primary content. |

## Quantitative mobile evidence

| Observation | Measured result |
| --- | ---: |
| Phone viewport | 390 × 844 px |
| Feed content before first card | 771 px |
| Results visible above fold | one card sliver |
| First card | 358 × 338 px |
| First thumbnail | 330 × 186 px |
| Feed page height | 9,852 px |
| VODs per page | 24 |
| Total pages | 125 |
| Episode masthead | 358 px tall |
| Player document position | 728 px |
| Player size | 356 × 200 px |
| Player share of viewport height | 23.7% |
| Transcript document position | 1,748 px |
| Transcript segments | 6,195 |
| Transcript landmarks | 42 |
| Small interactive targets detected on episode | 2,863 |
| Mobile episode layout shift | CLS ≈ 0.62 in this lab pass |
| Light-mode search contrast failures | 180 nodes per scan |
| Search-highlight contrast | 1.22:1; expected 4.5:1 |
| Empty-search horizontal overflow | 13 px |

## Highest-priority findings

### P0 — The mobile episode is not organized around watching

The player appears only near the bottom edge of the first viewport and is preceded by two empty secondary panels. Scrolling just 500 px after revealing it moves the player out of useful view. Transcript seeks therefore operate on invisible media.

Impact: the core promise—read a citation and verify it against the source—is materially harder on mobile.

Recommendation: create a dedicated mobile episode shell. Put an edge-to-edge 16:9 player immediately below the app bar. Keep it pinned under the app bar while the transcript sheet scrolls. Make title/details compact and collapsible. Place related episodes and quoted moments after the transcript or behind a Details tab; never place empty versions before the player.

### P0 — The transcript mounts an interaction surface far beyond mobile scale

The audited episode exposes 6,195 segments and thousands of sentence-level interactive targets in one route. The Chrome page grew tens of thousands of pixels, and the automated control scan found 2,863 undersized targets at 390 px. The current Split/Watch/Read modes are desktop concepts; “Split” is actually stacked on mobile.

Impact: visual density, DOM cost, keyboard burden, accidental taps, and loss of video context.

Recommendation: progressive transcript chapters should be the default, with only the current and adjacent chapter mounted. Use a virtualized or windowed transcript. On mobile, replace layout modes with sheet states: Transcript, Chapters, Details. A deliberate “Full transcript” mode can remain available for research.

Note: the untagged `rc.7` branch contains progressive transcript chapter work and search pagination that directly addresses part of this finding, but it does not change the player-first mobile hierarchy and was not the deployed release audited here.

### P0 — Search evidence is unreadable in light mode

axe found 180 contrast failures in the mobile light search page and another 180 in desktop light. Search `<mark>` text renders at approximately `#f1f1f4` over `#e8d5f1`, only 1.22:1 contrast.

Impact: the exact matching words—the most important content on the search page—are effectively erased for many users.

Recommendation: give highlights a dark semantic foreground in light mode and verify normal, active, selected, and dark variants at AA contrast.

### P0 — SPA navigation lacks deliberate scroll, focus, and title management

From feed scroll position 1,225 px, tapping the third card landed on the VOD route at 447 px rather than a defined top/player anchor. Back restored the feed position correctly. Search submission moved focus to `<body>` without announcing the new view. Returning from a VOD left the VOD title in the browser tab because most routes never update `document.title`.

Impact: users can land unpredictably mid-route; screen-reader users receive no route-change focus; history and tab labels become misleading.

Recommendation: add explicit route scroll restoration with per-link intent. Feed cards should open a VOD at the player anchor; browser Back should restore the feed. Move focus to the route `<h1>` (using `tabIndex=-1`) or announce route changes in a live region. Centralize route metadata and titles.

## Mobile feed diagnosis

### What makes it feel “last gen”

1. It is pagination-era browse UI: a large filter form, summary dashboard, Previous/Next controls, then a grid collapsed to one column.
2. It treats each VOD as a database record rather than a reason to watch. The title, channel, broadcast date, and update date often repeat what the thumbnail/date already says.
3. It lacks feed memory and momentum: no cursor loading, no “continue browsing,” no recent position, no compact filter chips, and no topical rails.
4. It uses hover elevation and image zoom as primary card affordances, neither of which adds value on touch.
5. It makes the user pay 771 px before seeing content.
6. The app icon itself resembles a hamburger, placed opposite the actual hamburger button, creating two competing menu-like glyphs in the mobile header.

### Recommended feed model

Use one content-first stream with a compact sticky control row:

- Search field or search affordance.
- Sort chip: Latest / Relevant / Longest.
- Filter chip that opens a bottom sheet for date, people, tags, and duration.
- Optional feed tabs: Latest, Topics, Moments.
- Cursor-based “load more” or infinite loading with a visible recovery control and retained scroll position.

Each VOD card should use:

- Edge-to-edge 16:9 thumbnail.
- One strong title line and one supporting line.
- Duration and date over the image, once.
- Two or three high-signal topic/person chips from archive intelligence.
- A short chapter or “what happened” preview when available.
- A clear primary action: Watch with transcript.
- Optional Save overflow action, not a full repeated action row.

At 390 px, target roughly 260–290 px per standard card so 1.5–2 cards are visible after the compact control row. Mix standard cards with denser rows for older results; avoid a 338 px invariant card for every VOD.

## Mobile episode redesign

### Proposed portrait structure

```text
┌──────────────────────────────┐
│ HasanAra        Search   ⋯   │  compact app bar
├──────────────────────────────┤
│                              │
│       16:9 source video      │  full-bleed, sticky
│                              │
├──────────────────────────────┤
│ 7:36:01  LIVE SYNC   ↗  ⋯    │  transport/source strip
├──────────────────────────────┤
│ August 10 broadcast     ⌄    │  compact collapsible title
├──────────────────────────────┤
│ Transcript | Chapters | Info │  sticky sheet tabs
├──────────────────────────────┤
│ Find in episode…             │
│ 00:15:00                     │
│ highlighted active sentence │  independently scrolling sheet
│ next transcript paragraph…  │
│                              │
├──────────────────────────────┤
│  Save     Share     Follow   │  thumb-reachable actions
└──────────────────────────────┘
```

Key behavior:

- The player is the first content after navigation and remains visible while reading.
- The transcript occupies the remaining viewport in a snap-point bottom sheet.
- Tapping a sentence seeks the visible player and preserves the sentence’s position.
- Dragging the sheet down emphasizes video; dragging it up emphasizes reading.
- Landscape promotes the player to immersive mode with a narrow transcript drawer.
- Fullscreen and “Open on YouTube” are explicit escape hatches.
- Related episodes and quoted moments live in Info or after the transcript; empty modules collapse to nothing.
- Split/Watch/Read are removed from mobile. Their useful intent is represented by sheet positions.

## Additional major findings

### P1 — Search results have excessive repeated actions

Each moment repeats Open moment, Play from here, Copy link, Copy quote, Save, and Full VOD. At 50 moments, this creates a wall of controls and 47 undersized controls in the mobile scan even before sentence-level VOD interactions.

Use the snippet itself as the primary open/seek action. Keep Save and Share visible; place copy variants and Full VOD in an overflow menu. Cluster nearby matches and progressively load results.

### P1 — Empty intelligence outranks primary content

“No explainable related episodes yet” and “No quoted moments have accumulated yet” occupy two large cards before the player. Empty secondary features should collapse, not block the primary source.

### P1 — Topic and Explore pages become data dumps on mobile

The Topic route exposes a very long timeline, accessibility table, evidence links, top VODs, and grouped results in one document. Explore begins with a long period selector whose option set spans many weeks and months. Both are technically complete but weak for phone discovery.

Use overview-first cards, horizontal period chips, a searchable period sheet, chart aggregation, progressive disclosure, and explicit “show evidence” actions.

### P1 — Feed controls are oversized and underpowered

The status block reports Shown, Total, Page, and Date in a large panel, followed by three full-width fields and top pagination. Yet navigation only supports Previous/Next across 125 pages.

Compress the status to one line (“2,992 VODs · newest first”), move advanced filters into a sheet, and use cursor loading. Preserve query and feed position in the URL/history.

### P1 — Large async layout shifts damage orientation

The lab pass observed CLS around 0.62 on the mobile episode, 0.66 at tablet, and 0.21 desktop. These values are indicative rather than field Core Web Vitals, but the screenshots and scroll tests confirm the cause: episode intelligence, player, outline, and a huge transcript arrive asynchronously and alter the document.

Reserve stable skeleton dimensions, mount a fixed mobile shell immediately, and progressively hydrate content within it.

### P1 — Mobile header has an icon-language collision

The brand icon looks like a black menu glyph while the actual menu button is another hamburger on the opposite side. Use a distinctive brand mark or wordmark-only treatment on mobile; reserve the hamburger shape exclusively for navigation.

### P1 — Text is often too small for the visual density

The interface uses many 9–11 px uppercase labels and metadata values. Although axe did not treat size alone as an AA failure, the repeated microtype becomes tiring on a high-density phone interface and weakens hierarchy.

Set a 12 px floor for nonessential metadata and 14 px for meaningful labels/actions. Preserve the archival tone with weight, case, and spacing rather than extreme reduction.

## Secondary findings

- The empty search page overflows horizontally by 13 px at 390 px.
- Six axe findings report `<aside>` landmarks nested inside other landmarks on Home and Saved.
- Most routes retain the generic `HasanAra` title; after visiting a VOD, history navigation can retain the stale VOD title.
- The mobile menu is usable and Escape-aware, but the current route indication needs to remain explicit in both expanded and collapsed states.
- Full-page screenshots reveal lazy thumbnails as blank placeholders until scrolled; they load correctly when brought into view, but placeholders should communicate image loading more intentionally.
- The YouTube embed returned “Video unavailable” in headless Chrome and emitted third-party ad/QoE request errors. The application’s source fallback exists, but the player state should include a first-party, styled explanation and direct source link outside the iframe.
- `Source video` uses very low-opacity text on black media chrome. Axe did not flag the composite in this run, but manual token review is warranted.
- The date-based home runtime format (`16378:37:29`) is machine-like. A human summary such as “16.4k hours” or “682 days” scans better.
- The current VOD count differs by context (2,944 archive summary versus 2,992 library records), which may be contractually valid but reads as inconsistency without explanation.

## What is already strong

- The archive’s citation-first proposition is immediately understandable.
- Search, topic, timeline, VOD, saved, login, and not-found routes all expose sensible primary headings.
- Form controls generally have programmatic labels; the Chrome accessibility tree found no unlabeled visible controls in the audited pages.
- No duplicate IDs or missing image `alt` attributes were detected.
- Theme switching works, and the dark-mode search highlights passed the axe contrast scan.
- Browser Back restored the VOD feed scroll position.
- The skip link appears first in keyboard order.
- Empty, loading, and error language is mostly plain and task-oriented.
- The visual system is recognizable and avoids generic SaaS aesthetics.

## Recommended delivery sequence

### Phase 0 — Safety and accessibility (1–2 days)

1. Fix light-mode `<mark>` contrast.
2. Add route title, focus, announcement, and intentional scroll restoration.
3. Remove the 13 px empty-search overflow.
4. Correct nested `<aside>` landmarks.
5. Hide empty pre-player intelligence panels.

### Phase 1 — Mobile episode shell (3–6 days)

1. Player first and edge-to-edge.
2. Sticky player plus transcript sheet.
3. Mobile-specific Transcript / Chapters / Info tabs.
4. Compact episode metadata and thumb-reachable actions.
5. Visible source fallback and landscape behavior.
6. Deep-link, seek, Back, rotation, and virtual-keyboard tests.

### Phase 2 — Mobile feed (3–5 days)

1. Compact sticky search/filter bar.
2. Bottom-sheet advanced filters.
3. Topic-rich, lower-height cards.
4. Cursor loading with retained scroll and recoverable errors.
5. Distinctive mobile brand mark and navigation treatment.

### Phase 3 — Information-density and performance pass (3–6 days)

1. Ship/validate progressive transcript chapters from `rc.7`.
2. Cluster and progressively load search moments.
3. Progressive disclosure for Topic and Explore.
4. Reduce repeated action rows and microtype.
5. Establish DOM budgets, lab CLS budgets, and real-user Web Vitals collection.

## Acceptance criteria for the redesign

- On 390 × 844, the player is fully visible without scrolling.
- Player remains visible while selecting and reading transcript sentences.
- No empty secondary module appears before the player.
- At least one full feed card and part of a second appear in the first content viewport.
- Advanced feed filters do not occupy the initial viewport.
- A transcript sentence tap seeks media without moving the sentence out of context.
- Mobile episode mounts a bounded number of transcript nodes.
- All WCAG 2.2 AA automated violations are zero in light and dark modes.
- Route transitions announce the new page, focus the heading, and use a documented scroll rule.
- Back restores feed position and filters.
- Every route has a correct, stable browser title.
- Search highlight contrast is at least 4.5:1.
- No horizontal overflow at 320, 360, 390, 768, or 1024 px.
- Lab CLS is below 0.1 on Home, Search, Feed, and Episode.
- Feed-to-player and search-to-citation journeys are covered in real Chrome at touch breakpoints.

## Evidence files

- `audit-results.json` — 33-page browser inventory.
- `axe-results.json` — 33 WCAG/best-practice scans.
- `mobile-deep-dive.json` — feed/player/transcript geometry and touch behavior.
- `navigation-deep-dive.json` — scroll, focus, title, and Back behavior.
- `summary.tsv` and `quantitative-summary.json` — compact metrics.
- PNG files — full-page and focused route screenshots.

