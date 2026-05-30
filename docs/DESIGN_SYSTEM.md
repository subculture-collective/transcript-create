# Design system

Transcript Search uses a technical, minimal SaaS interface: dense enough for transcript work, calm enough for long reading sessions, and consistent across app, billing, and admin surfaces.

## Direction

- Product type: transcript-search SaaS with workspace, billing, favorites, and admin dashboard surfaces.
- Tone: technical, minimal, editorial, trustworthy.
- Visual model: Swiss-modern grid, neutral surfaces, one trust-blue accent, orange reserved for conversion/CTA moments.
- Typography: `Satoshi` for UI and transcript reading. Avoid global serif; reserve serif only for explicitly editorial future surfaces.

## Tokens

Tokens live in `frontend/src/index.css` under Tailwind v4 `@theme`.

| Token | Light | Dark | Use |
| --- | --- | --- | --- |
| `canvas` | `#f8fafc` | `#0f172a` | App background |
| `surface` | `#ffffff` | `#111827` | Cards, header, panels |
| `surface-muted` | `#f1f5f9` | `#1e293b` | Nested cards, hover fills |
| `border` | `#e2e8f0` | `#334155` | Default borders |
| `border-strong` | `#cbd5e1` | `#475569` | Stronger dividers |
| `ink` | `#1e293b` | `#f8fafc` | Primary text |
| `muted` | `#64748b` | `#cbd5e1` | Secondary text |
| `subtle` | `#94a3b8` | `#94a3b8` | Timestamps, hints |
| `accent` | `#2563eb` | `#60a5fa` | Primary actions, links, active states |
| `accent-hover` | `#1d4ed8` | `#93c5fd` | Primary hover |
| `accent-soft` | `#dbeafe` | `#1e3a8a` | Active transcript/search highlights |
| `cta` | `#f97316` | `#fb923c` | Reserved for high-intent conversion |
| `success` | `#059669` | `#34d399` | Success state text/borders |
| `warning` | `#d97706` | `#fbbf24` | Warning/favorite state text/borders |
| `danger` | `#dc2626` | `#f87171` | Destructive actions |

## Utility primitives

Prefer these classes before adding one-off utility stacks:

- `page-title` — main page heading.
- `section-title` — section/card heading.
- `surface-card`, `surface-card-compact` — standard panels.
- `form-control` — input/select styling with 44px touch target and focus ring.
- `btn`, `btn-primary`, `btn-secondary`, `btn-ghost` — action variants.
- `nav-link`, `action-link`, `icon-button` — links and small controls.
- `badge-success`, `badge-warning` — status badges.
- `alert-info`, `alert-success`, `alert-warning` — feedback panels.
- `transcript-segment`, `transcript-segment-active`, `transcript-segment-favorite` — transcript workspace states.

## Rules

- Use semantic tokens (`bg-surface`, `text-muted`, `border-border`) instead of raw `gray-*`/`stone-*` for equivalent UI.
- All clickable surfaces need pointer affordance and visible focus.
- Hover states should change color/border/shadow only; avoid layout-shifting transforms.
- Keep transitions 150–300ms and respect `prefers-reduced-motion`.
- Use SVG icons from one consistent style; do not use emoji as UI icons/spinners in new work.
- App/workspace/admin surfaces should be dense (`p-3`/`p-4`, tight tables); marketing/pricing surfaces may breathe (`p-6`, larger gaps).
- Dark mode must be token-driven: no hardcoded light surfaces without a dark/token equivalent.

## Acceptance checklist

- [ ] Equivalent surfaces use the same primitive class.
- [ ] Buttons use `btn*`; inputs/selects use `form-control`.
- [ ] Links use `nav-link` or `action-link` by intent.
- [ ] No new scattered raw hex values or orphan `gray-*`/`stone-*` styles for semantic UI.
- [ ] Search, Video, Pricing, Favorites, Login, Upgrade, Admin, and modals remain coherent in dark mode.
- [ ] 320px, 768px, 1024px, and 1440px layouts avoid horizontal scroll.
- [ ] Keyboard focus is visible and tab order follows visual order.
