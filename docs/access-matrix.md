# Route, capability, and endpoint access matrix

**Status:** shipped contract (2026-07-12).

| Surface | Access |
| --- | --- |
| Home, search, Explore, episodes, timeline, topics, video, About, Support, Privacy, Terms | public |
| Donation configuration (`GET /support`) | public; returns only an allow-listed Stripe-hosted Payment Link or a disabled state |
| Saved and favorites | anonymous local-first; authenticated synchronization |
| Login | anonymous |
| Admin routes | authenticated plus `admin:access` capability |
| Search, public archive/video reads, suggestions, mention exports | public GET |
| Favorites, saved searches, profile | authenticated owner |
| Jobs list/read/write | authenticated owner or scoped API key (`jobs:read`, `jobs:write`) |
| Vocabulary mutation | authenticated owner; global management admin only |
| API key issuance | authenticated owner; admin scopes require audited admin issuance |
| Job requeue/quarantine/attempt administration and opinion correction | admin |
| Source deletion | owner or admin |

API-key read scopes are `search:read`, `videos:read`, `exports:read`, and `jobs:read`; mutation scope is `jobs:write`.
