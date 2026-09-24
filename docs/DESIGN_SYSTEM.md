# Design system

**Status:** shipped baseline (2026-07-12).

The React 19 frontend uses shared semantic classes in `frontend/src/index.css`: surfaces, archive sections, action links, buttons, badges, pills, alerts, and typography. Components must use theme tokens, targeted transitions, declared image dimensions, and no inline styles (required by CSP).

Light- and dark-theme text tokens must maintain at least WCAG AA 4.5:1 contrast on every semantic surface where they are used. Accent-filled controls use `text-accent-contrast`; invariant black media chrome uses `text-player-accent`; inline links within prose must include a non-color cue such as an underline.

Prefer presentational sections backed by query hooks, URL adapters, mutation controllers, and view models. Route state belongs in the URL when it must be shareable. All routes are lazy loaded; admin code must remain outside public route downloads. Gzip budgets are 150 KiB for the shell plus initial route and 100 KiB per lazy route.

## Broadsheet

**Status:** default design, 2026-09-23.

- **Editions.** The night edition (dark) is the primary design: newsprint black, warm off-white ink, and a signal red accent. The paper edition (light) uses off-white paper, black ink, and a deep red accent. The theme still follows the visitor's system preference until they toggle it.
- **Type.** Newsreader for headlines, chapter headings, and transcript text; Inter Tight for interface text. Episode titles and chapter headings are italic. A client profile font replaces these only when the profile sets `theme.font`.
- **Shape.** Tailwind's radius scale is squared off (0 to 3px). Panels drop borders and shadows for a heavy top rule in the ink colour (`--rule`), and the site header ends in a double rule.
- **Texture.** A fixed SVG noise layer adds newsprint grain behind content, and mastheads carry a halftone dot pattern that fades in from one side.
- **Motion.** Panel rules draw across on arrival, the open-paragraph rule draws down, chart bars rise, and spoken transcript text eases from grey to ink. Content never fades or slides in: opacity entrances failed contrast checks mid-animation, and translated entrances moved elements during layout-stability checks. `prefers-reduced-motion` stops all of these, including the ticker.
- **Tri-colour accents.** `accent-2`, `accent-3` and `player-accent` form a three-colour stripe at the top of the header and under the ticker label, and cycle through topic-density and chart marks. The masthead halftone uses `accent-2`. HasanAra's profile sets them to the Piker Broadcasting Service orange `#ff6633`, brick `#cd3333` and red `#ff3333`.
- **The Wire.** A ticker under the header (hidden below 40rem) scrolls archive topic cards with their recent mention counts, then trending and popular searches. It pauses on hover or focus; the duplicate reel used for looping is hidden from assistive technology.

## Episode reading surface

**Status:** redesigned 2026-09-23.

- **Layout.** On wide screens the player, episode timeline strip, and navigator (Chapters, Topics, Moments, Related) sit in a rail pinned beside the transcript (`.transcript-rail`). Below 64rem the player docks at the top, and a resizable sheet holds Transcript, Chapters, Topics, and Info tabs.
- **Transcript.** Formatted blocks are split into paragraphs of roughly 80 words that end on a sentence boundary (`.transcript-paragraph`), set in the reading face (`--font-reading`). Chapter titles appear as headings inside the text. Progressive loading mounts three sections at a time and brings in the next section as the reader approaches the end.
- **Passage actions.** Selecting a sentence opens its paragraph and shows `SectionActions`: Play from here, Copy quote, Copy link, Save, and Share passage. Selection never starts playback. The margin timecode plays directly, and Escape closes the passage.
- **Reading progress.** `PlaybackProgress` updates the DOM without re-rendering the transcript. Spoken sentences carry `data-played`, the current sentence carries `.transcript-sentence-current` with a `--sweep` percentage, and the document carries `data-progress="on"` once playback has a position. Upcoming text uses the `subtle` token so it stays within the contrast rule above.
- **Topics in an episode.** `findEpisodeTopics` counts whole-word matches of archive topic cards (with aliases), tags, people, and popular searches in the loaded transcript. These counts are literal phrase matches, not classifier output, and the UI describes them that way.
- **Positioned graphics.** The episode strip, topic density rows, and search insight bars use SVG geometry attributes, because the content security policy forbids inline `style` attributes. Colors come from the stylesheet.
