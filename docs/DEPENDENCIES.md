# Dependencies

**Status:** shipped contract (2026-07-12).

Python production dependencies are split between `requirements-api.txt` and `requirements-worker.txt`, with shared pins in `constraints.txt`. Development-only tooling is in `requirements-dev.txt`. Core is headless and has no frontend or browser-test dependencies; those belong to archive frontends and the `rekolekt-web` kit.

Python 3.11 is required. `make verify` runs pip-audit. Stripe is not a code dependency: voluntary support redirects to a validated Stripe-hosted Payment Link, while billing remains disabled.
